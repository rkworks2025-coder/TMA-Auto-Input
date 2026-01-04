import sys
import os
import time
import datetime
import json
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
# ログインIDはハイフンで分割して入力する仕様
LOGIN_ID_FULL = "0030-927583" 
LOGIN_PW = "Ccj-222223"
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

def click_strict(driver, selector_or_xpath):
    """クリックできなければ即例外発生（テスト失敗）"""
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
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可: {sel}") from e

def input_strict(driver, selector_or_id, value):
    """入力できなければ即例外発生"""
    if selector_or_id.startswith("/") or selector_or_id.startswith("("):
        by_method = By.XPATH
        sel = selector_or_id
    else:
        by_method = By.CSS_SELECTOR
        sel = selector_or_id if (selector_or_id.startswith("#") or "." in selector_or_id) else f"#{selector_or_id}"
    
    try:
        el = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((by_method, sel)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {sel}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗: {sel}") from e

def select_radio_strict(driver, name_attr, value):
    """ラジオボタン選択（name属性とvalue値で特定）"""
    xpath = f"//input[@name='{name_attr}' and @value='{value}']"
    try:
        # ラジオボタンそのものか、親要素をクリック
        el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
        driver.execute_script("arguments[0].click();", el)
        print(f"   [OK] Radio: {name_attr}={value}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_Radio_{name_attr}")
        raise Exception(f"ラジオボタン選択失敗: {name_attr}={value}") from e

def switch_tab(driver, tab_text):
    """タブ切り替え"""
    xpath = f"//a[contains(text(), '{tab_text}')] | //li[contains(text(), '{tab_text}')] | //div[contains(@class,'tab') and contains(text(), '{tab_text}')]"
    try:
        click_strict(driver, xpath)
        time.sleep(1.0)
    except Exception as e:
        print(f"   [WARNING] Tab '{tab_text}' click failed, trying specific logic.")

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
    print("=== Automation Start (Integrated Version) ===")

    # 1. 引数取得 (JSONペイロード)
    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        # YAML修正後のJSON形式で受け取る
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        
        target_plate = data.get('plate')
        target_url = data.get('target_url')
        tire_data = data.get('tire_data', {})
        
        print(f"Target Plate: {target_plate}")
        print(f"URL: {target_url}")
        
        if not target_plate or not tire_data:
            raise Exception("Plate or Tire Data missing")

    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # --- [1] ログイン (成功実績のあるロジック) ---
        print("\n--- [1] ログイン開始 ---")
        driver.get(target_url)
        
        # ★ここが重要：IDを分割して入力する
        id_parts = LOGIN_ID_FULL.split("-")
        input_strict(driver, "#cardNo1", id_parts[0])
        input_strict(driver, "#cardNo2", id_parts[1])
        input_strict(driver, "#password", LOGIN_PW)
        
        # ログインボタン
        click_strict(driver, ".btn-primary, input[type='submit']")
        
        # --- [1.5] メニュー画面 ---
        # ログイン後、メニュー画面が出ることがあるので、あれば「点検」または「検索」へ
        # URLでsearchが含まれていれば既に一覧
        time.sleep(2)
        if "search" not in driver.current_url:
             print("\n--- [1.5] メニュー回避 / 一覧へ遷移 ---")
             # 成功ファイルにあったロジックを使用
             try:
                 click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")
             except:
                 pass # 既に一覧にいる可能性

        # --- [2] 車両特定 & 日常点検開始 ---
        print("\n--- [2] 日常点検フェーズ ---")
        wait_for_index(driver)
        
        # 対象車両の行にある「日常点検」ボタンを押す
        # XPath: プレート番号を含むセルの行(tr)の中にあるリンク
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        routine_btn_xpath = f"{row_xpath}//a[contains(@href, 'RoutineInspection') or contains(text(), '日常点検')]"
        
        click_strict(driver, routine_btn_xpath)
        
        # --- [3] 日常点検入力 (仕様定義書準拠) ---
        print("\n--- [3] 入力実行: 日常点検 ---")
        
        # 1. エンジンルーム (Default)
        select_radio_strict(driver, "engineOilAmount", "1")
        select_radio_strict(driver, "brakeLiquid", "1")
        select_radio_strict(driver, "radiatorWater", "1")
        select_radio_strict(driver, "batteryLiquid", "1")
        select_radio_strict(driver, "windowWasherLiquid", "2") # ★OK補充
        
        # 2. タイヤ
        switch_tab(driver, "タイヤ")
        select_radio_strict(driver, "tireType", "1")
        select_radio_strict(driver, "tireDamage", "1")
        
        # タイヤデータ入力 (RF->LF->LR->RR)
        # RF
        input_strict(driver, "input[name='tireMfrFrontRightCm']", tire_data['rf']['week'])
        input_strict(driver, "input[name='tireGrooveFrontRightCmIp']", str(tire_data['rf']['depth']).split('.')[0])
        if '.' in str(tire_data['rf']['depth']):
            input_strict(driver, "input[name='tireGrooveFrontRightCmFp']", str(tire_data['rf']['depth']).split('.')[1])
        input_strict(driver, "input[name='tirePressureFrontRightCm']", tire_data['rf']['press'])
        input_strict(driver, "input[name='tirePressureAdjustedFrontRightCm']", tire_data['rf']['press'])

        # LF
        input_strict(driver, "input[name='tireMfrFrontLeftCm']", tire_data['lf']['week'])
        input_strict(driver, "input[name='tireGrooveFrontLeftCmIp']", str(tire_data['lf']['depth']).split('.')[0])
        if '.' in str(tire_data['lf']['depth']):
            input_strict(driver, "input[name='tireGrooveFrontLeftCmFp']", str(tire_data['lf']['depth']).split('.')[1])
        input_strict(driver, "input[name='tirePressureFrontLeftCm']", tire_data['lf']['press'])
        input_strict(driver, "input[name='tirePressureAdjustedFrontLeftCm']", tire_data['lf']['press'])

        # LR
        input_strict(driver, "input[name='tireMfrRearLeftBi4']", tire_data['lr']['week'])
        input_strict(driver, "input[name='tireGrooveRearLeftBi4Ip']", str(tire_data['lr']['depth']).split('.')[0])
        if '.' in str(tire_data['lr']['depth']):
            input_strict(driver, "input[name='tireGrooveRearLeftBi4Fp']", str(tire_data['lr']['depth']).split('.')[1])
        input_strict(driver, "input[name='tirePressureRearLeftBi4']", tire_data['lr']['press'])
        input_strict(driver, "input[name='tirePressureAdjustedRearLeftBi4']", tire_data['lr']['press'])

        # RR
        input_strict(driver, "input[name='tireMfrRearRightBi4']", tire_data['rr']['week'])
        input_strict(driver, "input[name='tireGrooveRearRightBi4Ip']", str(tire_data['rr']['depth']).split('.')[0])
        if '.' in str(tire_data['rr']['depth']):
            input_strict(driver, "input[name='tireGrooveRearRightBi4Fp']", str(tire_data['rr']['depth']).split('.')[1])
        input_strict(driver, "input[name='tirePressureRearRightBi4']", tire_data['rr']['press'])
        input_strict(driver, "input[name='tirePressureAdjustedRearRightBi4']", tire_data['rr']['press'])

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

        # 7. トランク (再度 車載品タブ)
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

        # ★洗車不要(2)
        select_radio_strict(driver, "exteriorDirt", "2")

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
