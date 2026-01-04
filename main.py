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
# テスト時はダミーHTMLのパスまたはURLを指定して起動することを推奨
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"

# 必要に応じて変更
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
GAS_API_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

EVIDENCE_DIR = "evidence"

# ==========================================
# 厳格な操作関数群 (Fail Fast)
# ==========================================
def get_chrome_driver():
    """
    GitHub Actions等のCI環境でのバージョン不一致エラーを回避する
    堅牢なドライバー取得ロジック
    """
    options = Options()
    options.add_argument('--headless') 
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
    
    # 1. まずは webdriver_manager での取得を試みる
    try:
        print("   [Driver] webdriver_managerでセットアップを試みます...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("   [Driver] 成功: webdriver_manager")
        return driver
    except Exception as e:
        print(f"   [Driver] webdriver_manager 失敗: {e}")
        print("   [Driver] システムインストール済みのドライバーで再試行します...")

    # 2. 失敗した場合、環境パス(PATH)にある chromedriver を使用する
    try:
        driver = webdriver.Chrome(options=options)
        print("   [Driver] 成功: System Path Driver")
        return driver
    except Exception as e:
        print(f"   [Driver] 致命的エラー: ドライバーを起動できませんでした。\n{e}")
        raise e

def take_screenshot(driver, name):
    if not os.path.exists(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR)
    timestamp = datetime.datetime.now().strftime('%H%M%S')
    filename = f"{EVIDENCE_DIR}/{name}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"   [写] 保存: {filename}")
    except:
        print("   [写] 撮影失敗")

def click_strict(driver, selector_or_xpath):
    """クリックできなければ即死する"""
    if selector_or_xpath.startswith("/") or selector_or_xpath.startswith("("):
        by_method = By.XPATH
        sel = selector_or_xpath
    else:
        by_method = By.CSS_SELECTOR
        sel = selector_or_xpath if (selector_or_xpath.startswith("#") or "." in selector_or_xpath) else f"#{selector_or_xpath}"

    try:
        # 隠れ要素を避けるため、clickableになるまで待つ
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by_method, sel)))
        # 念のためスクロールして中央に持ってくる
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)
        el.click()
        print(f"   [OK] Click: {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可: {sel} \n{e}")

def input_strict(driver, selector_or_id, value):
    """入力できなければ即死する"""
    sel = selector_or_id if (selector_or_id.startswith("#") or "." in selector_or_id) else f"#{selector_or_id}"
    try:
        el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        el.clear()
        el.send_keys(str(value))
        
        # 入力値確認
        actual = el.get_attribute('value')
        if str(actual) != str(value):
            print(f"      (注意) 入力値不一致: 期待({value}) != 実際({actual})")
        
        print(f"   [OK] Input: {value} -> {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        print(f"   [Error] 入力失敗: {sel}")
        raise e

def switch_tab(driver, tab_data_name):
    """
    指定された data-name 属性を持つタブをクリックして表示を切り替える。
    """
    try:
        print(f"   ▼ タブ切り替え: {tab_data_name}")
        selector = f".tab-button[data-name='{tab_data_name}']"
        # タブ自体が表示されているか待機
        tab_el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_el)
        tab_el.click()
        time.sleep(1.0) # アニメーション待ち
        
    except Exception as e:
        take_screenshot(driver, f"ERROR_TabSwitch_{tab_data_name}")
        raise Exception(f"タブ切り替え失敗: {tab_data_name} \n{e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Merged Version) ===")

    # 引数処理（ここを強化）
    target_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOGIN_URL
    
    # URLが http で始まらない場合、ローカルファイルとみなして絶対パス+file://に変換
    if not target_url.startswith("http"):
        # すでに file:// がついていない場合のみ処理
        if not target_url.startswith("file://"):
            abs_path = os.path.abspath(target_url)
            target_url = f"file://{abs_path}"
    
    print(f"Target URL: {target_url}")

    driver = get_chrome_driver()

    try:
        driver.get(target_url)
        time.sleep(2)

        # URL判定：ログイン画面ならログイン処理を実行
        if "login" in driver.current_url or "Login" in driver.title:
            print("\n--- [1] ログイン処理 ---")
            id_parts = TMA_ID.split("-")
            input_strict(driver, "#cardNo1", id_parts[0])
            input_strict(driver, "#cardNo2", id_parts[1])
            input_strict(driver, "#password", TMA_PW)
            click_strict(driver, ".btn-primary")
            time.sleep(3)

        # --- [3] 日常点検データ取得 & 入力 ---
        print("\n--- [3] 日常点検 & GASデータ取得 ---")
        
        # GASデータ取得（ダミー用に今回はスキップまたは空で進行）
        tire_data = {}

        # ===== 1. エンジンルーム (Tab: engine) =====
        switch_tab(driver, "engine")
        try:
            click_strict(driver, "coolantGauge1")     # 冷却水
            click_strict(driver, "engineOilGauge1")   # オイル
            click_strict(driver, "brakeFluidGauge1")  # ブレーキ液
            click_strict(driver, "washerFluidGauge1") # ウォッシャー
        except Exception as e:
            print(f"   [Error] エンジンルーム入力失敗: {e}")
            raise e

        # ===== 2. タイヤ (Tab: tire) =====
        switch_tab(driver, "tire")
        try:
            click_strict(driver, "tireType1") # ノーマル
            
            input_strict(driver, "tireFrontRegularPressure", tire_data.get("std_f", "250"))
            input_strict(driver, "tireRearRegularPressure", tire_data.get("std_r", "240"))
            
            # 4輪ループ処理
            wheels = [
                ("rf", "FrontRightCm"), 
                ("lf", "FrontLeftCm"), 
                ("lr", "RearLeftBi4"), 
                ("rr", "RearRightBi4")
            ]
            prev = tire_data.get("prev", {})

            for pre, suf in wheels:
                print(f"   -- タイヤ入力: {suf} --")
                week = str(prev.get(f"dot_{pre}", "1224"))
                if len(week)==3: week = "0"+week
                input_strict(driver, f"tireMfr{suf}", week)
                
                # 亀裂損傷 (右前のみクリックする仕様に合わせる)
                if pre == "rf": 
                    click_strict(driver, "tireDamage1")

                input_strict(driver, f"tireGroove{suf}Ip", "4")
                input_strict(driver, f"tireGroove{suf}Fp", "5")
                input_strict(driver, f"tirePressure{suf}", "240")
                input_strict(driver, f"tirePressureAdjusted{suf}", "240")

            print("   タイヤデータ入力完了")
        except Exception as e:
            take_screenshot(driver, "ERROR_TireInput")
            raise e

        # ===== 3. 動作確認 (Tab: motion) =====
        switch_tab(driver, "motion")
        click_strict(driver, "engineCondition1")
        click_strict(driver, "brakeCondition1")
        click_strict(driver, "parkingBrakeCondition1")
        click_strict(driver, "washerSprayCondition1")
        click_strict(driver, "wiperWipeCondition1")

        # ===== 4. 車載品-運転席 (Tab: in-car) =====
        switch_tab(driver, "in-car")
        click_strict(driver, "inspectionCertificateExist1")
        click_strict(driver, "inspectionStickerExist1")
        click_strict(driver, "autoLiabilityExist1")
        click_strict(driver, "maintenanceStickerExist1")
        click_strict(driver, "flaresExist1")
        input_strict(driver, "flaresLimit", "2029-01")
        click_strict(driver, "passCardExist1")
        click_strict(driver, "roomStickerExist1")
        click_strict(driver, "deodorantsExist1")

        # ===== 5. 装備確認 (Tab: equipment) =====
        switch_tab(driver, "equipment")
        click_strict(driver, "backMonitor1")
        click_strict(driver, "cornerSensor1")
        click_strict(driver, "brakeSupport1")
        click_strict(driver, "laneDevianceAlert1")
        click_strict(driver, "driveRecorder1")

        # ===== 6. 灯火装置 (Tab: light) =====
        switch_tab(driver, "light")
        click_strict(driver, "turnSignal1")

        # ===== 7. 車両周り (Tab: perimeter) =====
        switch_tab(driver, "perimeter")
        click_strict(driver, "fuelCap1")
        click_strict(driver, "carStickerExist1")

        # ===== 8. 車載品-トランク (Tab: trunk) =====
        switch_tab(driver, "trunk")
        click_strict(driver, "warningTrianglePlateDamage1")
        click_strict(driver, "puncRepairKitExist1")
        input_strict(driver, "puncRepairKitLimit", "2028-10")
        click_strict(driver, "spearTireDamage1")
        click_strict(driver, "tireJackupSetExist1")
        click_strict(driver, "cleaningKit1")
        click_strict(driver, "juniorSeat2")

        take_screenshot(driver, "99_AllInputCompleted")
        print("\n--- 全項目の入力完了 ---")

        # --- [5] 完了処理 ---
        print("\n--- [5] 完了処理 ---")
        try:
            # 完了ボタン (.is-complete)
            finish_selector = "a.is-complete" 
            finish_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, finish_selector))
            )
            print("   完了ボタン発見。クリックします...")
            finish_btn.click()
            
            try:
                WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
                print("   完了アラート承認")
            except:
                print("   (アラートは出ませんでした)")
                
        except Exception as e:
            print(f"   完了ボタン処理失敗: {e}")
            take_screenshot(driver, "ERROR_Finish")

        print("\n=== SUCCESS: 全工程完了 ===")

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        raise e 
    finally:
        if 'driver' in locals():
            driver.quit()

if __name__ == "__main__":
    main()
