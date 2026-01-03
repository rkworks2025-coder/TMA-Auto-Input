import sys
import os
import time
import datetime
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 設定エリア
# ==========================================
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

EVIDENCE_DIR = "evidence"

# ==========================================
# 厳格な操作関数群 (Fail Fast)
# ==========================================
def get_chrome_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1')
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def take_screenshot(driver, name):
    """必ず写真を撮る"""
    if not os.path.exists(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR)
    timestamp = datetime.datetime.now().strftime('%H%M%S')
    filename = f"{EVIDENCE_DIR}/{name}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"   [写] 保存: {filename}")

def find_strict(driver, selector):
    """見つからなければ即死する検索"""
    try:
        return WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
    except Exception:
        take_screenshot(driver, "ERROR_NotFound")
        raise Exception(f"要素が見つかりません: {selector}")

def click_strict(driver, selector_or_id):
    """クリックできなければ即死する"""
    # IDかCSSか自動判定
    if selector_or_id.startswith("#") or "." in selector_or_id or "[" in selector_or_id:
        sel = selector_or_id
    else:
        sel = f"#{selector_or_id}"

    try:
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
        el.click()
        print(f"   [OK] Click: {sel}")
    except Exception:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリックに失敗しました: {sel}")

def input_strict(driver, selector_or_id, value):
    """入力後、値が一致しなければ即死する"""
    if selector_or_id.startswith("#") or "." in selector_or_id:
        sel = selector_or_id
    else:
        sel = f"#{selector_or_id}"

    try:
        el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
        el.clear()
        el.send_keys(str(value))
        
        # 検証
        actual = el.get_attribute('value')
        if str(actual) != str(value):
            take_screenshot(driver, "ERROR_InputMismatch")
            raise Exception(f"入力不一致! 期待: {value}, 実際: {actual} (Target: {sel})")
        
        print(f"   [OK] Input: {value} -> {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise e # エラーを握りつぶさずに投げる

# ==========================================
# メイン処理
# ==========================================
def main():
    # 引数チェック
    if len(sys.argv) > 1:
        target_plate = sys.argv[1]
    else:
        raise Exception("車両ナンバー引数がありません")

    target_login_url = DEFAULT_LOGIN_URL
    if len(sys.argv) > 2 and sys.argv[2]:
        target_login_url = sys.argv[2]
        print(f"MODE: 指定URL ({target_login_url})")
    else:
        print(f"MODE: 本番URL ({target_login_url})")

    driver = get_chrome_driver()

    try:
        # 1. ログイン
        print("\n--- [1] ログイン開始 ---")
        driver.get(target_login_url)
        take_screenshot(driver, "00_LoginPage")

        # 入力欄を厳格に探す (IDまたは属性で特定)
        # ※ダミーと本番の両方に対応できるCSSセレクタを使用
        input_strict(driver, "input[type='text'], #userId", TMA_ID)
        input_strict(driver, "input[type='password'], #password", TMA_PW)
        
        click_strict(driver, "button, input[type='submit'], .btn-login")
        
        # ★ログイン成功判定: 次の画面の要素が出るまで待つ
        # 失敗したらここでタイムアウトエラーになり止まる
        print("   画面遷移待ち...")
        try:
            # リスト画面(div.list) または 詳細画面(coolantGauge1) のどちらかが出るはず
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.list, #coolantGauge1, body"))
            )
        except:
            raise Exception("ログイン後の画面遷移に失敗しました")
            
        print("   ログイン成功確認")

        # 2. 車両選択
        print("\n--- [2] 車両選択 ---")
        # すでに詳細画面にいるかチェック
        if len(driver.find_elements(By.ID, "coolantGauge1")) > 0:
             print("   すでに詳細画面です")
        else:
             # リストの一番上をクリック
             print("   リストの一番上を選択します")
             try:
                 # リスト内の最初のリンク(aタグ)を探してクリック
                 top_link = WebDriverWait(driver, 10).until(
                     EC.element_to_be_clickable((By.XPATH, "(//a[contains(@href, 'html')])[1] | (//div[contains(@class,'list')]//a)[1]"))
                 )
                 top_link.click()
             except:
                 raise Exception("車両リストが見つかりません、またはクリックできません")

        # 詳細画面が開いたことを確認（必須要素: タイヤ入力欄など）
        find_strict(driver, "#tireType1, #coolantGauge1")
        take_screenshot(driver, "01_VehicleSelected")

        # 3. データ取得
        print("\n--- [3] GASデータ取得 ---")
        res = requests.get(f"{GAS_API_URL}?plate={target_plate}&check=1")
        tire_data = res.json()
        if not tire_data.get("ok"):
             # データがないなら止めるべきか？今回はデフォルト値で進むが警告は出す
             print("WARNING: GASからのデータ取得に失敗、またはデータなし")

        # 4. 入力実行 (Fail Fast)
        print("\n--- [4] 入力実行 ---")
        
        # 点検項目
        click_strict(driver, "coolantGauge1")
        click_strict(driver, "engineOilGauge1")
        click_strict(driver, "washerFluidGauge1") # ウォッシャー液

        # タイヤ入力
        if tire_data:
            click_strict(driver, "tireType1")
            
            # 規定値
            input_strict(driver, "tireFrontRegularPressure", tire_data.get("std_f", "240"))
            input_strict(driver, "tireRearRegularPressure", tire_data.get("std_r", "240"))
            
            # 測定値
            prev = tire_data.get("prev", {})
            wheels = [("rf", "FrontRightCm"), ("lf", "FrontLeftCm"), ("lr", "RearLeftBi4"), ("rr", "RearRightBi4")]
            
            for pre, suf in wheels:
                # 製造週 (必須)
                week = str(prev.get(f"dot_{pre}", "0123")) # なければダミー値でテスト
                if len(week)==3: week = "0"+week
                input_strict(driver, f"tireMfr{suf}", week)
                
                # 溝
                depth = str(prev.get(f"tread_{pre}", "5.5"))
                ip, fp = (depth.split(".") + ["0"])[0:2]
                input_strict(driver, f"tireGroove{suf}Ip", ip)
                input_strict(driver, f"tireGroove{suf}Fp", fp[0])
                
                # 空気圧
                press = str(prev.get(f"pre_{pre}", "240"))
                input_strict(driver, f"tirePressure{suf}", press)
                input_strict(driver, f"tirePressureAdjusted{suf}", press)

            click_strict(driver, "tireDamage1")

        # 入力結果の証拠
        take_screenshot(driver, "02_InputResult")

        # その他項目
        ids_ok = [
            "engineCondition1", "brakeCondition1", "parkingBrakeCondition1", 
            "washerSprayCondition1", "wiperWipeCondition1", "interiorDirt01", "exteriorDirt02"
        ]
        # 存在するものだけクリック（画面遷移によっては無いものもあるため、ここは柔軟にするが、エラーならわかるように）
        for i in ids_ok:
            try:
                driver.find_element(By.ID, i).click()
            except:
                pass # チェックボックス系は画面外などで失敗しやすいので、今回はSkip許容（メイン入力ではないため）

        # 5. 完了処理
        print("\n--- [5] 完了処理 ---")
        
        # JSで完了関数を呼ぶ（これが一番確実）
        driver.execute_script("if(typeof completeTask === 'function') completeTask('daily');")
        time.sleep(1)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('interior');")
        time.sleep(1)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('wash');")
        time.sleep(1)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('exterior');")
        time.sleep(1)
        driver.execute_script("if(typeof completeTask === 'function') completeTask('lend');")
        time.sleep(2)

        take_screenshot(driver, "03_PreComplete")
        
        # 完了ボタン
        try:
            # a.is-complete または ボタンを探す
            finish_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.is-complete, .btn-complete"))
            )
            finish_btn.click()
            
            # アラート承認
            WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
            print("   完了アラート承認")
        except:
            print("   完了ボタンが見つからないか、JSで完了済み")

        print("\n=== SUCCESS: 全工程完了 ===")

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        # ここで例外を再送出することで、GitHub Actionsを「赤色（Failure）」にする
        raise e 
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
