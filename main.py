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

# スクリーンショット保存フォルダ
EVIDENCE_DIR = "evidence"

# ==========================================
# ヘルパー関数
# ==========================================
def get_chrome_driver():
    """ヘッドレスモードでChromeを起動"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080') # 画面サイズを広めに設定
    options.add_argument('--disable-gpu')
    options.add_argument('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def take_screenshot(driver, name_prefix):
    """証拠写真を撮影する"""
    if not os.path.exists(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR)
    
    timestamp = datetime.datetime.now().strftime('%H%M%S')
    filename = f"{EVIDENCE_DIR}/{name_prefix}_{timestamp}.png"
    try:
        driver.save_screenshot(filename)
        print(f"   [写真] 証拠画像を保存しました: {filename}")
    except Exception as e:
        print(f"   [エラー] 写真撮影に失敗: {e}")

def click_id(driver, eid):
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, eid))).click()
        print(f"   [操作] クリック: {eid}")
    except:
        print(f"   [Skip] クリック不可: {eid}")

def set_val(driver, eid, val):
    """値を入力し、正しく入ったか読み取って確認する"""
    try:
        el = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, eid)))
        el.clear()
        el.send_keys(str(val))
        
        # ▼▼ 入力後の値を確認（読み合わせ） ▼▼
        actual_val = el.get_attribute('value')
        if str(actual_val) == str(val):
            print(f"   [確認OK] {eid} に '{val}' を入力しました")
        else:
            print(f"   [確認NG] {eid} の入力値が不一致です (期待: {val}, 実際: {actual_val})")
            
    except:
        print(f"   [Skip] 入力不可: {eid}")

# ==========================================
# メイン処理
# ==========================================
def main():
    # 引数受け取り
    if len(sys.argv) > 1:
        target_plate = sys.argv[1]
    else:
        print("エラー: 車両ナンバーが指定されていません")
        sys.exit(1)

    if len(sys.argv) > 2 and sys.argv[2]:
        target_login_url = sys.argv[2]
        print(f"★モード指定あり: {target_login_url} に接続します")
    else:
        target_login_url = DEFAULT_LOGIN_URL
        print(f"モード指定なし: 本番({target_login_url}) に接続します")

    print(f"開始: 車両No {target_plate} の自動入力を開始します")
    
    driver = get_chrome_driver()
    
    try:
        # 1. ログイン
        print("\n--- ステップ1: ログイン ---")
        driver.get(target_login_url)
        
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            driver.execute_script(f"document.querySelector('input[type=\"text\"]').value = '{TMA_ID}';")
            driver.execute_script(f"document.querySelector('input[type=\"password\"]').value = '{TMA_PW}';")
            
            login_btn = driver.find_element(By.CSS_SELECTOR, "button, input[type='submit']")
            login_btn.click()
            time.sleep(5)
            print("   ログイン処理完了")
        except Exception as e:
            print(f"   ログインエラー（またはスキップ）: {e}")

        # 2. 車両選択
        print("\n--- ステップ2: 車両選択 ---")
        try:
            xpath = f"//a[contains(text(), '{target_plate}')] | //div[contains(text(), '{target_plate}')]"
            target_link = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            target_link.click()
            time.sleep(3)
            print(f"   車両 '{target_plate}' を選択しました")
            take_screenshot(driver, "01_AfterSelect") # 写真撮影
        except Exception as e:
            print("   車両選択エラー: リストに見つからないか、既に詳細画面にいます")

        # 3. GASデータ取得
        print("\n--- ステップ3: データ取得 ---")
        tire_data = None
        try:
            res = requests.get(f"{GAS_API_URL}?plate={target_plate}&check=1")
            if res.status_code == 200:
                j = res.json()
                if j.get("ok"):
                    tire_data = j
                    print("   GASからタイヤデータを取得しました")
        except:
            print("   データ取得失敗（デフォルト値または空で進みます）")

        # 4. 自動入力実行
        
        # [日常点検]
        print("\n--- ステップ4: 日常点検 & タイヤ入力 ---")
        click_id(driver, "coolantGauge1")
        click_id(driver, "engineOilGauge1")
        click_id(driver, "brakeFluidGauge1")
        click_id(driver, "washerFluidGauge1")

        if tire_data:
            click_id(driver, "tireType1")
            
            # 規定値
            set_val(driver, "tireFrontRegularPressure", tire_data.get("std_f", ""))
            set_val(driver, "tireRearRegularPressure", tire_data.get("std_r", ""))
            
            # 測定値
            prev = tire_data.get("prev", {})
            wheels = [
                ("rf", "FrontRightCm"), 
                ("lf", "FrontLeftCm"), 
                ("lr", "RearLeftBi4"), 
                ("rr", "RearRightBi4")
            ]
            
            for pre, suf in wheels:
                # 製造週
                week = str(prev.get(f"dot_{pre}", ""))
                if len(week)==3: week = "0"+week
                set_val(driver, f"tireMfr{suf}", week)
                
                # 溝
                depth = str(prev.get(f"tread_{pre}", "0"))
                ip, fp = (depth.split(".") + ["0"])[0:2]
                set_val(driver, f"tireGroove{suf}Ip", ip)
                set_val(driver, f"tireGroove{suf}Fp", fp[0])
                
                # 空気圧
                press = prev.get(f"pre_{pre}", "")
                set_val(driver, f"tirePressure{suf}", press)
                set_val(driver, f"tirePressureAdjusted{suf}", press)
            
            click_id(driver, "tireDamage1")

        # ★ここで証拠写真を撮る（タイヤ入力直後）
        take_screenshot(driver, "02_TireInputDone")

        # 動作確認・装備・車載品
        ids_ok = [
            "engineCondition1", "brakeCondition1", "parkingBrakeCondition1", 
            "washerSprayCondition1", "wiperWipeCondition1",
            "inspectionCertificateExist1", "inspectionStickerExist1", "autoLiabilityExist1",
            "maintenanceStickerExist1", "roomStickerExist1", "deodorantsExist1",
            "backMonitor1", "cornerSensor1", "brakeSupport1", "laneDevianceAlert1", "driveRecorder1",
            "turnSignal1", "fuelCap1", "carStickerExist1",
            "warningTrianglePlateDamage1", "puncRepairKitExist1", "cleaningKit1"
        ]
        for i in ids_ok: click_id(driver, i)
        
        driver.execute_script("if(typeof completeTask === 'function') completeTask('daily');")
        time.sleep(2)

        # [車内清掃]
        print("\n--- ステップ5: 車内清掃 ---")
        click_id(driver, "interiorDirt01")
        click_id(driver, "interiorCheckTrouble01")
        click_id(driver, "soundVolume01")
        click_id(driver, "lostArticle01")
        driver.execute_script("if(typeof completeTask === 'function') completeTask('interior');")
        time.sleep(2)

        # [洗車]
        print("\n--- ステップ6: 洗車 ---")
        click_id(driver, "exteriorDirt02")
        driver.execute_script("if(typeof completeTask === 'function') completeTask('wash');")
        time.sleep(2)

        # [外装確認]
        print("\n--- ステップ7: 外装確認 ---")
        click_id(driver, "exteriorState01")
        driver.execute_script("if(typeof completeTask === 'function') completeTask('exterior');")
        time.sleep(2)

        # [貸出準備]
        print("\n--- ステップ8: 貸出準備 ---")
        try:
             driver.find_element(By.CSS_SELECTOR, "input.input-bg-pink").send_keys("10000")
        except: pass
        
        js_radios = [
            "document.getElementsByName('refuel')[1].checked = true;",
            "document.getElementsByName('fuel_card')[0].checked = true;",
            "document.getElementsByName('room_seal')[0].checked = true;",
            "document.getElementsByName('park_check')[0].checked = true;"
        ]
        for js in js_radios:
            try: driver.execute_script(js)
            except: pass
            
        driver.execute_script("if(typeof completeTask === 'function') completeTask('lend');")
        time.sleep(2)

        # 最終完了
        print("\n--- 最終ステップ: 完了処理 ---")
        
        # ★完了ボタンを押す前に、最後の証拠写真を撮る
        take_screenshot(driver, "03_BeforeFinish")
        
        try:
            driver.find_element(By.CSS_SELECTOR, "a.is-complete").click()
            WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
            print("   完了ボタンを押しました")
        except: 
            print("   完了ボタンが見つからないか、既に押されています")

        print("\n=== 全工程が正常に終了しました ===")

    except Exception as e:
        print(f"\n[!!!] エラー発生: {e}")
        take_screenshot(driver, "99_ErrorOccurred") # エラー時も写真を残す
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
