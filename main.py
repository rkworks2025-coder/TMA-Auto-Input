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

# ------------------------------------------------------------------
# ヘルパー関数
# ------------------------------------------------------------------
def setup_driver():
    options = Options()
    options.add_argument('--headless') # 本番はヘッドレス推奨
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1280,1080')
    # UserAgent設定（スマホビュー回避のためPC用を指定）
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
    driver = webdriver.Chrome(options=options)
    return driver

def click_element(driver, xpath, desc="Element"):
    try:
        wait = WebDriverWait(driver, 10)
        elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        elem.click()
        print(f"Clicked: {desc}")
        time.sleep(1.5) # 画面遷移待ち
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
    """ name属性とvalue値でラジオボタンを選択 """
    try:
        xpath = f"//input[@name='{name_attr}' and @value='{value}']"
        elem = driver.find_element(By.XPATH, xpath)
        # ラジオボタン自体が見えない場合、親のlabelをクリックする等の対応が必要な場合があるが
        # 基本的にはJS実行または直接クリックで試行
        driver.execute_script("arguments[0].click();", elem)
        print(f"Selected {name_attr}={value}")
    except NoSuchElementException:
        print(f"Radio {name_attr}={value} not found, skipping.")

def switch_tab(driver, tab_text):
    """ タブのテキスト部分を含まれる要素をクリックして切り替え """
    try:
        # タブは通常 <a>タグや <li>タグ内のテキストで識別
        xpath = f"//a[contains(text(), '{tab_text}')] | //li[contains(text(), '{tab_text}')]"
        elem = driver.find_element(By.XPATH, xpath)
        elem.click()
        print(f"Switched Tab: {tab_text}")
        time.sleep(1.5)
    except NoSuchElementException:
        print(f"Tab '{tab_text}' not found.")

def wait_for_index(driver):
    """ インデックス画面（車両一覧）に戻るまで待機 """
    print("Waiting for Index page...")
    try:
        # URLの変化や、特定の要素（例: 検索ボタンやログアウトボタン）で判定
        WebDriverWait(driver, 20).until(
            EC.url_contains("search")  # URLに search が含まれる＝一覧画面と仮定
        )
        print("Returned to Index.")
        time.sleep(2)
    except TimeoutException:
        print("Warning: Timed out waiting for Index page.")

# ------------------------------------------------------------------
# 各フェーズの実装
# ------------------------------------------------------------------

def phase1_routine_inspection(driver, tire_data):
    """ 日常点検フェーズ """
    print("\n--- Phase 1: Routine Inspection ---")
    
    # 1. エンジンルーム (Default Tab)
    # ※IDが不明なため、標準的な推測IDを使用。現場でエラーが出る場合はID修正が必要。
    # エンジンオイル, ブレーキ液, 冷却水, バッテリー液 -> 1 (OK)
    select_radio(driver, "engineOilAmount", "1")
    select_radio(driver, "brakeLiquid", "1")
    select_radio(driver, "radiatorWater", "1")
    select_radio(driver, "batteryLiquid", "1")
    # ウォッシャー液 -> 2 (OK補充) ★指示対応
    select_radio(driver, "windowWasherLiquid", "2") 

    # 2. タイヤ (Tab: tire)
    switch_tab(driver, "タイヤ")
    
    # 共通設定
    select_radio(driver, "tireType", "1") # ノーマル
    select_radio(driver, "tireDamage", "1") # 亀裂OK

    # 4輪データ入力
    # 右前 (RF) - Suffix: FrontRightCm
    input_text(driver, "tireMfrFrontRightCm", tire_data['rf']['week'])
    input_text(driver, "tireGrooveFrontRightCmIp", str(tire_data['rf']['depth']).split('.')[0])
    # 小数が無い場合は0を入れるなどの処理が必要だが、一旦そのまま
    if '.' in str(tire_data['rf']['depth']):
        input_text(driver, "tireGrooveFrontRightCmFp", str(tire_data['rf']['depth']).split('.')[1])
    input_text(driver, "tirePressureFrontRightCm", tire_data['rf']['press'])
    input_text(driver, "tirePressureAdjustedFrontRightCm", tire_data['rf']['press'])

    # 左前 (LF) - Suffix: FrontLeftCm
    input_text(driver, "tireMfrFrontLeftCm", tire_data['lf']['week'])
    input_text(driver, "tireGrooveFrontLeftCmIp", str(tire_data['lf']['depth']).split('.')[0])
    if '.' in str(tire_data['lf']['depth']):
        input_text(driver, "tireGrooveFrontLeftCmFp", str(tire_data['lf']['depth']).split('.')[1])
    input_text(driver, "tirePressureFrontLeftCm", tire_data['lf']['press'])
    input_text(driver, "tirePressureAdjustedFrontLeftCm", tire_data['lf']['press'])

    # 左後 (LR) - Suffix: RearLeftBi4
    input_text(driver, "tireMfrRearLeftBi4", tire_data['lr']['week'])
    input_text(driver, "tireGrooveRearLeftBi4Ip", str(tire_data['lr']['depth']).split('.')[0])
    if '.' in str(tire_data['lr']['depth']):
        input_text(driver, "tireGrooveRearLeftBi4Fp", str(tire_data['lr']['depth']).split('.')[1])
    input_text(driver, "tirePressureRearLeftBi4", tire_data['lr']['press'])
    input_text(driver, "tirePressureAdjustedRearLeftBi4", tire_data['lr']['press'])

    # 右後 (RR) - Suffix: RearRightBi4
    input_text(driver, "tireMfrRearRightBi4", tire_data['rr']['week'])
    input_text(driver, "tireGrooveRearRightBi4Ip", str(tire_data['rr']['depth']).split('.')[0])
    if '.' in str(tire_data['rr']['depth']):
        input_text(driver, "tireGrooveRearRightBi4Fp", str(tire_data['rr']['depth']).split('.')[1])
    input_text(driver, "tirePressureRearRightBi4", tire_data['rr']['press'])
    input_text(driver, "tirePressureAdjustedRearRightBi4", tire_data['rr']['press'])

    # 3. 動作確認 (Tab: motion)
    switch_tab(driver, "動作確認")
    select_radio(driver, "engineCondition", "1")
    select_radio(driver, "brakeCondition", "1")
    select_radio(driver, "parkingBrakeCondition", "1")
    select_radio(driver, "washerSprayCondition", "1")
    select_radio(driver, "wiperWipeCondition", "1")

    # 4. 車載品 - 運転席 (Tab: in-car)
    switch_tab(driver, "車載品") # "車載品"タブが複数ある場合、HTML構造に依存。通常は最初のヒットでOK
    select_radio(driver, "inspectionCertificateExist", "1")
    select_radio(driver, "inspectionStickerExist", "1")
    select_radio(driver, "autoLiabilityExist", "1")
    select_radio(driver, "maintenanceStickerExist", "1")
    select_radio(driver, "roomStickerExist", "1")
    select_radio(driver, "deodorantsExist", "1")

    # 5. 装備確認 (Tab: equipment)
    switch_tab(driver, "装備確認")
    select_radio(driver, "backMonitor", "1")
    select_radio(driver, "cornerSensor", "1")
    select_radio(driver, "brakeSupport", "1")
    select_radio(driver, "laneDevianceAlert", "1")
    select_radio(driver, "driveRecorder", "1")

    # 6. 灯火装置 & 車両周り (Tab: light)
    switch_tab(driver, "灯火装置")
    select_radio(driver, "turnSignal", "1")
    switch_tab(driver, "車両周り")
    select_radio(driver, "fuelCap", "1")
    select_radio(driver, "carStickerExist", "1")

    # 7. 車載品 - トランク (Tab: trunk)
    # 再度「車載品」だが、TMAの構造上、タブ名が同じだと失敗する可能性あり。
    # もし失敗する場合は "トランク" というキーワードを探すロジックに変更が必要。
    # ここでは仕様書の順序通り、最後のタブとして処理。
    try:
        # トランク用の車載品タブをクリック（簡易的に最後のli要素などを狙うか、テキストで判別）
        # 一旦 "車載品" でトライし、ダメならXPath調整が必要
        switch_tab(driver, "車載品") 
    except:
        pass
    
    select_radio(driver, "warningTrianglePlateDamage", "1")
    select_radio(driver, "puncRepairKitExist", "1")
    select_radio(driver, "cleaningKit", "1")

    # 完了アクション：一時保存
    click_element(driver, "//input[@value='一時保存'] | //button[contains(text(), '一時保存')]", "Temporary Save Button")
    wait_for_index(driver)


def phase2_interior_cleaning(driver, plate):
    """ 車内清掃フェーズ """
    print("\n--- Phase 2: Interior Cleaning ---")
    # インデックスで対象車両の「車内清掃」ボタンを探してクリック
    # ※実際はテーブル構造からplateを探し、その行の「車内清掃」ボタンを押す必要がある
    # 簡易実装：画面内の「車内清掃」リンク/ボタンをクリック（対象車両詳細に入っている前提ではないので注意）
    # ★重要：一度インデックスに戻っているので、再度「対象車両」を見つけて、その行のボタンを押すロジックが必要。
    # ここでは「詳細画面に入り直す」のではなく「一覧画面のボタン」を想定。
    
    # 対象車両の行を特定するXPath（例）
    row_xpath = f"//td[contains(text(), '{plate}')]/.." 
    
    # 車内清掃ボタン（鉛筆マークやテキストなど）
    # 定義書にファイル情報があるので、ボタンクリックで遷移
    btn_xpath = f"{row_xpath}//a[contains(@href, 'InteriorCleaning') or contains(text(), '車内清掃')]"
    click_element(driver, btn_xpath, "Interior Cleaning Link")

    select_radio(driver, "interiorDirt", "1")
    select_radio(driver, "interiorCheckTrouble", "1")
    select_radio(driver, "soundVolume", "1")
    select_radio(driver, "lostArticle", "1")

    click_element(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]", "Done Button")
    wait_for_index(driver)


def phase3_car_wash(driver, plate):
    """ 洗車フェーズ """
    print("\n--- Phase 3: Car Wash ---")
    row_xpath = f"//td[contains(text(), '{plate}')]/.."
    btn_xpath = f"{row_xpath}//a[contains(@href, 'CarWash') or contains(text(), '洗車')]"
    click_element(driver, btn_xpath, "Car Wash Link")

    # ★指示対応：洗車不要(2)
    select_radio(driver, "exteriorDirt", "2")

    click_element(driver, "//input[@value='完了'] | //button[contains(text(), '完了')]", "Done Button")
    wait_for_index(driver)


def phase4_exterior_check(driver, plate):
    """ 外装確認フェーズ """
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
    # 引数・ペイロード取得
    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
        
    try:
        payload_str = sys.argv[1]
        payload = json.loads(payload_str)
        client_payload = payload.get('client_payload', {})
        
        target_plate = client_payload.get('plate')
        target_url = client_payload.get('target_url')
        tire_data = client_payload.get('tire_data', {})
        
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
        
        # ID/PW入力（ID属性は実際のサイトに合わせて調整が必要な場合あり。通常は user_id / password）
        input_text(driver, "userId", LOGIN_ID)
        input_text(driver, "password", LOGIN_PW)
        click_element(driver, "//input[@type='submit' or @type='button']", "Login Button")
        
        # 2. 車両検索（インデックス画面）
        wait_for_index(driver)
        
        # 検索ボックスに入力して検索（もしあれば）
        # input_text(driver, "search_plate", target_plate)
        # click_element(driver, "//button[contains(text(), '検索')]", "Search Button")
        
        # --- Phase 1: Routine Inspection (Tire & Others) ---
        # 対象車両の行から「日常点検」ボタンを探す
        row_xpath = f"//td[contains(text(), '{target_plate}')]/.."
        routine_btn_xpath = f"{row_xpath}//a[contains(@href, 'RoutineInspection') or contains(text(), '日常点検')]"
        click_element(driver, routine_btn_xpath, "Routine Inspection Link")
        
        # 日常点検実行
        phase1_routine_inspection(driver, tire_data)
        
        # --- Phase 2: Interior Cleaning ---
        phase2_interior_cleaning(driver, target_plate)
        
        # --- Phase 3: Car Wash ---
        phase3_car_wash(driver, target_plate)
        
        # --- Phase 4: Exterior Check ---
        phase4_exterior_check(driver, target_plate)
        
        print("\nAll Phases Completed Successfully.")
        
    except Exception as e:
        print(f"\nExecution Failed: {e}")
        # デバッグ用にソースを出力する場合はコメントアウト解除
        # print(driver.page_source)
        sys.exit(1)
        
    finally:
        driver.quit()
        print("Driver Closed. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
