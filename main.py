import os
import sys
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ------------------------------------------------------------------
# 設定・定数
# ------------------------------------------------------------------
LOGIN_ID = "0030-927583"
LOGIN_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ------------------------------------------------------------------
# ヘルパー関数
# ------------------------------------------------------------------
def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1280,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    driver = webdriver.Chrome(options=options)
    return driver

def save_screenshot(driver, filename):
    if not os.path.exists(EVIDENCE_DIR):
        os.makedirs(EVIDENCE_DIR)
    path = os.path.join(EVIDENCE_DIR, filename)
    driver.save_screenshot(path)
    print(f"Screenshot saved: {path}")

def click_element(driver, xpath, desc="Element"):
    try:
        wait = WebDriverWait(driver, 10)
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        elem.click()
        print(f"Clicked: {desc}")
        time.sleep(1.5)
    except Exception as e:
        print(f"Error clicking {desc}: {e}")
        raise

def input_text(driver, name_attr, value):
    if not value: return
    try:
        elem = driver.find_element(By.NAME, name_attr)
        elem.clear()
        elem.send_keys(str(value))
        print(f"Input {name_attr}: {value}")
    except NoSuchElementException:
        print(f"Skipped {name_attr} (Not found)")

def select_radio(driver, name_attr, value):
    try:
        xpath = f"//input[@name='{name_attr}' and @value='{value}']"
        elem = driver.find_element(By.XPATH, xpath)
        driver.execute_script("arguments[0].click();", elem)
        print(f"Selected {name_attr}={value}")
    except NoSuchElementException:
        print(f"Radio {name_attr}={value} not found, skipping.")

def switch_tab(driver, tab_text):
    try:
        xpath = f"//a[contains(text(), '{tab_text}')] | //li[contains(text(), '{tab_text}')]"
        elem = driver.find_element(By.XPATH, xpath)
        elem.click()
        print(f"Switched Tab: {tab_text}")
        time.sleep(1.5)
    except NoSuchElementException:
        print(f"Tab '{tab_text}' not found.")

def wait_for_index(driver):
    print("Waiting for Index page...")
    try:
        WebDriverWait(driver, 20).until(
            EC.url_contains("search")
        )
        print("Returned to Index.")
        time.sleep(2)
    except TimeoutException:
        print("Warning: Timed out waiting for Index page.")

# ------------------------------------------------------------------
# 各フェーズの実装
# ------------------------------------------------------------------

def phase1_routine_inspection(driver, tire_data):
    print("\n--- Phase 1: Routine Inspection ---")
    
    # 1. エンジンルーム
    select_radio(driver, "engineOilAmount", "1")
    select_radio(driver, "brakeLiquid", "1")
    select_radio(driver, "radiatorWater", "1")
    select_radio(driver, "batteryLiquid", "1")
    select_radio(driver, "windowWasherLiquid", "2") # OK補充

    # 2. タイヤ
    switch_tab(driver, "タイヤ")
    select_radio(driver, "tireType", "1")
    select_radio(driver, "tireDamage", "1")

    # 4輪データ入力
    # RF
    input_text(driver, "tireMfrFrontRightCm", tire_data['rf']['week'])
    input_text(driver, "tireGrooveFrontRightCmIp", str(tire_data['rf']['depth']).split('.')[0])
    if '.' in str(tire_data['rf']['depth']):
        input_text(driver, "tireGrooveFrontRightCmFp", str(tire_data['rf']['depth']).split('.')[1])
    input_text(driver, "tirePressureFrontRightCm", tire_data['rf']['press'])
    input_text(driver, "tirePressureAdjustedFrontRightCm", tire_data['rf']['press'])

    # LF
    input_text(driver, "tireMfrFrontLeftCm", tire_data['lf']['week'])
    input_text(driver, "tireGrooveFrontLeftCmIp", str(tire_data['lf']['depth']).split('.')[0])
    if '.' in str(tire_data['lf']['depth']):
        input_text(driver, "tireGrooveFrontLeftCmFp", str(tire_data['lf']['depth']).split('.')[1])
    input_text(driver, "tirePressureFrontLeftCm", tire_data['lf']['press'])
    input_text(driver, "tirePressureAdjustedFrontLeftCm", tire_data['lf']['press'])

    # LR
    input_text(driver, "tireMfrRearLeftBi4", tire_data['lr']['week'])
    input_text(driver, "tireGrooveRearLeftBi4Ip", str(tire_data['lr']['depth']).split('.')[0])
    if '.' in str(tire_data['lr']['depth']):
        input_text(driver, "tireGrooveRearLeftBi4Fp", str(tire_data['lr']['depth']).split('.')[1])
    input_text(driver, "tirePressureRearLeftBi4", tire_data['lr']['press'])
    input_text(driver, "tirePressureAdjustedRearLeftBi4", tire_data['lr']['press'])

    # RR
    input_text(driver, "tireMfrRearRightBi4", tire_data['rr']['week'])
    input_text(driver, "tireGrooveRearRightBi4Ip", str(tire_data['rr']['depth']).split('.')[0])
    if '.' in str(tire_data['rr']['depth']):
        input_text(driver, "tireGrooveRearRightBi4Fp", str(tire_data['rr']['depth']).split('.')[1])
    input_text(driver, "tirePressureRearRightBi4", tire_data['rr']['press'])
    input_text(driver, "tirePressureAdjustedRearRightBi4", tire_data['rr']['press'])

    # 3. 動作確認
    switch_tab(driver, "動作確認")
    select_radio(driver, "engineCondition", "1")
    select_radio(driver, "brakeCondition", "1")
    select_radio(driver, "parkingBrakeCondition", "1")
    select_radio(driver, "washerSprayCondition", "1")
    select_radio(driver, "wiperWipeCondition", "1")

    # 4. 車載品 - 運転席
    switch_tab(driver, "車載品")
    select_radio(driver, "inspectionCertificateExist", "1")
    select_radio(driver, "inspectionStickerExist", "1")
    select_radio(driver, "autoLiabilityExist", "1")
    select_radio(driver, "maintenanceStickerExist", "1")
    select_radio(driver, "roomStickerExist", "1")
    select_radio(driver, "deodorantsExist", "1")

    # 5. 装備確認
    switch_tab(driver, "装備確認")
    select_radio(driver, "backMonitor", "1")
    select_radio(driver, "cornerSensor", "1")
    select_radio(driver, "brakeSupport", "1")
    select_radio(driver, "laneDevianceAlert", "1")
    select_radio(driver, "driveRecorder", "1")

    # 6. 灯火装置 & 車両周り
    switch_tab(driver, "灯火装置")
    select_radio(driver, "turnSignal", "1")
    switch_tab(driver, "車両周り")
    select_radio(driver, "fuelCap", "1")
    select_radio(driver, "carStickerExist", "1")

    # 7. 車載品 - トランク
    try:
        switch_tab(driver, "車載品") 
    except:
        pass
    
    select_radio(driver, "warningTrianglePlateDamage", "1")
    select_radio(driver, "puncRepairKitExist", "1")
    select_radio(driver, "cleaningKit", "1")

    # 完了
    click_element(driver, "//input[@value='一時保存'] | //button[contains(text(), '一時保存')]", "Temporary Save Button")
    wait_for_index(driver)


def phase2_interior_cleaning(driver, plate):
    print("\n--- Phase 2: Interior Cleaning ---")
    row_xpath = f"//td[contains(text(), '{plate}')]/.." 
    btn_xpath = f"{row_xpath}//a[contains(@href, 'InteriorCleaning') or contains(text(), '車内清掃')]"
    click_element(driver, btn_xpath, "Interior Cleaning Link")

    select_radio(driver, "interiorDirt", "1")
    select_radio(driver, "interiorCheckTrouble", "1")
    select_radio(driver, "soundVolume", "1")
    select_radio(driver, "lostArticle", "1")

    click_element(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]", "Done Button")
    wait_for_index(driver)


def phase3_car_wash(driver, plate):
    print("\n--- Phase 3: Car Wash ---")
    row_xpath = f"//td[contains(text(), '{plate}')]/.."
    btn_xpath = f"{row_xpath}//a[contains(@href, 'CarWash') or contains(text(), '洗車')]"
    click_element(driver, btn_xpath, "Car Wash Link")

    select_radio(driver, "exteriorDirt", "2") # 洗車不要

    click_element(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]", "Done Button")
    wait_for_index(driver)


def phase4_exterior_check(driver, plate):
    print("\n--- Phase 4: Exterior Check ---")
    row_xpath = f"//td[contains(text(), '{plate}')]/.."
    btn_xpath = f"{row_xpath}//a[contains(@href, 'ExteriorCheck') or contains(text(), '外装')]"
    click_element(driver, btn_xpath, "Exterior Check Link")

    select_radio(driver, "exteriorState", "1")

    click_element(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]", "Done Button")
    wait_for_index(driver)


# ------------------------------------------------------------------
# メイン処理
# ------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
        
    try:
        # ★修正: YAMLでJSON化されているのでそのまま読み込む
        # 余計な 'client_payload' キーの探索を廃止
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        
        target_plate = data.get('plate')
        target_url = data.get('target_url')
        tire_data = data.get('tire_data', {})
        
        print(f"Target Plate: {target_plate}")
        print(f"URL: {target_url}")

        if not target_plate or not tire_data:
            print("Error: Missing plate or tire_data.")
            sys.exit(1)

    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = setup_driver()

    try:
        # 1. ログイン
        driver.get(target_url)
        print("Opened Login Page.")
        
        input_text(driver, "userId", LOGIN_ID)
        input_text(driver, "password", LOGIN_PW)
        click_element(driver, "//input[@type='submit' or @type='button']", "Login Button")
        
        # 2. 車両検索（インデックス画面）
        wait_for_index(driver)
        
        # --- Phase 1 ---
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        routine_btn_xpath = f"{row_xpath}//a[contains(@href, 'RoutineInspection') or contains(text(), '日常点検')]"
        click_element(driver, routine_btn_xpath, "Routine Inspection Link")
        
        phase1_routine_inspection(driver, tire_data)
        
        # --- Phase 2 ---
        phase2_interior_cleaning(driver, target_plate)
        
        # --- Phase 3 ---
        phase3_car_wash(driver, target_plate)
        
        # --- Phase 4 ---
        phase4_exterior_check(driver, target_plate)
        
        print("\nAll Phases Completed Successfully.")
        sys.exit(0) # 正常終了

    except Exception as e:
        # ★修正: エラー内容を隠さず表示し、証拠写真を撮って異常終了する
        print(f"\nExecution Failed: {e}")
        save_screenshot(driver, "error_screenshot.png")
        sys.exit(1)
        
    finally:
        # ★修正: ここで sys.exit(0) をしてはいけない。ドライバを閉じるだけ。
        driver.quit()
        print("Driver Closed.")

if __name__ == "__main__":
    main()
