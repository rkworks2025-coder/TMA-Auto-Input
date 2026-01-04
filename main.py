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
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

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

def determine_selector(selector_str):
    """
    文字列からXPathかCSSセレクタか、単なるIDかを判定して返す
    ★修正: '[' や '.' を含む場合はそのままCSSセレクタとして扱う
    """
    if selector_str.startswith("/") or selector_str.startswith("("):
        return By.XPATH, selector_str
    
    # CSSセレクタとみなす条件: #, ., [, >, : を含む場合
    if any(char in selector_str for char in ['#', '.', '[', ']', '>', ':']):
        return By.CSS_SELECTOR, selector_str
    
    # それ以外はIDとみなして # を付与
    return By.CSS_SELECTOR, f"#{selector_str}"

def click_strict(driver, selector_str):
    """クリックできなければ即例外発生"""
    by_method, sel = determine_selector(selector_str)

    try:
        el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by_method, sel)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可: {sel}") from e

def input_strict(driver, selector_str, value):
    """入力できなければ即例外発生"""
    by_method, sel = determine_selector(selector_str)
    
    try:
        el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((by_method, sel)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗: {sel}") from e

def select_radio_strict(driver, name_attr, value):
    """ラジオボタン選択"""
    xpath = f"//input[@name='{name_attr}' and @value='{value}']"
    try:
        el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
        driver.execute_script("arguments[0].click();", el)
        print(f"   [OK] Radio: {name_attr}={value}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_Radio_{name_attr}")
        raise Exception(f"ラジオボタン選択失敗: {name_attr}={value}") from e

def switch_tab(driver, tab_text):
    """タブ切り替え"""
    xpath = f"//div[contains(@class,'tab-button')][contains(.,'{tab_text}')] | //li[contains(text(),'{tab_text}')] | //a[contains(text(),'{tab_text}')]"
    try:
        click_strict(driver, xpath)
        time.sleep(1.0)
        print(f"   -> タブ切り替え: {tab_text}")
    except Exception as e:
        print(f"   [WARNING] Tab '{tab_text}' click failed.")

def wait_for_index(driver):
    """一覧画面に戻るのを待機"""
    print("   一覧画面への遷移を待機中...")
    try:
        WebDriverWait(driver, 20).until(EC.url_contains("search"))
        time.sleep(2)
        print("   -> 一覧画面に戻りました")
    except:
        take_screenshot(driver, "ERROR_ReturnIndex")
        raise Exception("一覧画面に戻れませんでした")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fixed Selector Logic) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        
        target_plate = data.get('plate')
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        
        print(f"Target Plate: {target_plate}")
        print(f"URL: {target_url}")

        if not target_plate:
            raise Exception("Plate Data missing")

    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # --- [1] ログイン ---
        print("\n--- [1] ログイン開始 ---")
        driver.get(target_url)
        
        id_parts = TMA_ID.split("-")
        input_strict(driver, "#cardNo1", id_parts[0])
        input_strict(driver, "#cardNo2", id_parts[1])
        input_strict(driver, "#password", TMA_PW)
        click_strict(driver, ".btn-primary") # または input[type='submit']
        
        # --- [1.5] メニュー回避 ---
        print("\n--- [1.5] メニュー画面遷移 ---")
        try:
             click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")
        except:
             pass 

        # --- [2] 車両リスト選択 & ポップアップ ---
        print("\n--- [2] 車両リスト選択 & 開始ポップアップ ---")
        inspection_btn_xpath = f"//td[contains(text(), '{target_plate}')]/..//a[contains(text(), '点検')]"
        
        try:
            click_strict(driver, inspection_btn_xpath)
        except:
            print(f"   Target plate {target_plate} not found, trying generic inspection button.")
            click_strict(driver, "(//div[contains(@class, 'other-btn-area')]//a[contains(text(), '点検')])[1]")

        print("   ポップアップ: 表示待機中...")
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "posupMessageConfirm"))
        )
        click_strict(driver, "#posupMessageConfirmOk")

        # --- [2.5] トップ画面 (点検開始処理) ---
        print("\n--- [2.5] トップ画面 (点検開始) ---")
        click_strict(driver, "#startBtnContainer a")
        
        print("   トップ画面: 『日常点検』ボタン有効化待機...")
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#dailyBtnContainer a"))
        )
        time.sleep(1) 
        click_strict(driver, "#dailyBtnContainer a")
        
        # --- [3] 日常点検入力 ---
        print("\n--- [3] 入力実行: 日常点検 ---")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # 1. エンジンルーム
        print("   [Step 1] エンジンルーム")
        try:
            select_radio_strict(driver, "engineOilAmount", "1")
            select_radio_strict(driver, "brakeLiquid", "1")
            select_radio_strict(driver, "radiatorWater", "1")
            select_radio_strict(driver, "batteryLiquid", "1")
            select_radio_strict(driver, "windowWasherLiquid", "2")
        except:
            click_strict(driver, "coolantGauge1")
            click_strict(driver, "engineOilGauge1")
            click_strict(driver, "washerFluidGauge1")

        # 2. タイヤ
        print("   [Step 2] タイヤ")
        switch_tab(driver, "タイヤ")
        select_radio_strict(driver, "tireType", "1")
        select_radio_strict(driver, "tireDamage", "1")

        # タイヤデータ入力 (RF->LF->LR->RR)
        # ★ここが重要: 修正された input_strict により input[name=...] が正しく機能する
        wheels = [
            ('rf', 'FrontRightCm'), 
            ('lf', 'FrontLeftCm'), 
            ('lr', 'RearLeftBi4'), 
            ('rr', 'RearRightBi4')
        ]

        for pos, suffix in wheels:
            d = tire_data.get(pos, {})
            # 週
            input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
            
            # 溝 (整数・小数)
            depth_str = str(d.get('depth', '5.5'))
            if '.' in depth_str:
                ip, fp = depth_str.split('.')
            else:
                ip, fp = depth_str, '0'
            
            input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
            # 小数部フィールドがある場合のみ入力（try-exceptで囲むか、存在チェック推奨だがStrictでいく）
            # 定義書にFpがあると書いてあるので入力
            input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
            
            # 空気圧
            press = d.get('press', '')
            input_strict(driver, f"input[name='tirePressure{suffix}']", press)
            input_strict(driver, f"input[name='tirePressureAdjusted{suffix}']", press)

        # 3. 動作確認
        switch_tab(driver, "動作確認")
        select_radio_strict(driver, "engineCondition", "1")
        select_radio_strict(driver, "brakeCondition", "1")
        select_radio_strict(driver, "parkingBrakeCondition", "1")
        select_radio_strict(driver, "washerSprayCondition", "1")
        select_radio_strict(driver, "wiperWipeCondition", "1")

        # 4. 車載品 (運転席)
        switch_tab(driver, "車載品")
        select_radio_strict(driver, "inspectionCertificateExist", "1")
        select_radio_strict(driver, "inspectionStickerExist", "1")
        select_radio_strict(driver, "autoLiabilityExist", "1")
        select_radio_strict(driver, "maintenanceStickerExist", "1")
        select_radio_strict(driver, "roomStickerExist", "1")
        select_radio_strict(driver, "deodorantsExist", "1")

        # 5. 装備確認
        switch_tab(driver, "装備確認")
        select_radio_strict(driver, "backMonitor", "1")
        select_radio_strict(driver, "cornerSensor", "1")
        select_radio_strict(driver, "brakeSupport", "1")
        select_radio_strict(driver, "laneDevianceAlert", "1")
        select_radio_strict(driver, "driveRecorder", "1")

        # 6. 灯火/車両周り
        switch_tab(driver, "灯火装置")
        select_radio_strict(driver, "turnSignal", "1")
        switch_tab(driver, "車両周り")
        select_radio_strict(driver, "fuelCap", "1")
        select_radio_strict(driver, "carStickerExist", "1")

        # 7. トランク
        try:
             click_strict(driver, "(//a[contains(text(), '車載品')])[2] | //a[contains(text(), '車載品')]")
        except:
             pass
        select_radio_strict(driver, "warningTrianglePlateDamage", "1")
        select_radio_strict(driver, "puncRepairKitExist", "1")
        select_radio_strict(driver, "cleaningKit", "1")

        # 一時保存
        print("   一時保存をクリック...")
        click_strict(driver, "//input[@value='一時保存'] | //button[contains(text(), '一時保存')]")
        wait_for_index(driver)

        # --- [4] 車内清掃フェーズ ---
        print("\n--- [4] 車内清掃フェーズ ---")
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        btn_xpath = f"{row_xpath}//a[contains(@href, 'InteriorCleaning') or contains(text(), '車内清掃')]"
        click_strict(driver, btn_xpath)

        select_radio_strict(driver, "interiorDirt", "1")
        select_radio_strict(driver, "interiorCheckTrouble", "1")
        select_radio_strict(driver, "soundVolume", "1")
        select_radio_strict(driver, "lostArticle", "1")

        click_strict(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]")
        wait_for_index(driver)

        # --- [5] 洗車フェーズ ---
        print("\n--- [5] 洗車フェーズ ---")
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        btn_xpath = f"{row_xpath}//a[contains(@href, 'CarWash') or contains(text(), '洗車')]"
        click_strict(driver, btn_xpath)

        select_radio_strict(driver, "exteriorDirt", "2") # 洗車不要

        click_strict(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]")
        wait_for_index(driver)

        # --- [6] 外装確認フェーズ ---
        print("\n--- [6] 外装確認フェーズ ---")
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        btn_xpath = f"{row_xpath}//a[contains(@href, 'ExteriorCheck') or contains(text(), '外装')]"
        click_strict(driver, btn_xpath)

        select_radio_strict(driver, "exteriorState", "1")

        click_strict(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]")
        wait_for_index(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR (Test Failed) [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
