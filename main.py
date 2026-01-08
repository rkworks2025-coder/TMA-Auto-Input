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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()import sys
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
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"

# ==========================================
# 例外設定（位置指定: 0始まり）
# 基本は 0 (一番左) を選ぶが、ここは指定の位置を選ぶ
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 左から2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 左から2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# 厳格な操作関数群
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

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Click: {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_ClickFailed")
        raise Exception(f"クリック不可 (Timeout): {selector_str}") from e

def click_main_action_button(driver, button_type):
    """一時保存/完了ボタンクリック"""
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"
    print(f"   画面上の「{label}」ボタンを探しています...")
    try:
        el = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print(f"   [OK] Main Action Click: {label}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_MainAction_{label}")
        raise Exception(f"「{label}」ボタンが見つかりません (Timeout)。") from e

def click_section_button(driver, section_title):
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath, timeout=30)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_popups(driver):
    """ポップアップ処理"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 
    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """テキスト入力"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def wait_for_return_page(driver):
    """遷移待機"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# 新・自動入力ロジック (Safe Fill & Position Based)
# ==========================================
def fill_section_radios(driver, section_xpath):
    """
    指定エリア内のラジオボタンを自動処理する
    - 既に選択済みなら何もしない (上書き防止)
    - 未選択ならデフォルト位置(0)を選択
    - 例外リストにある名前なら指定位置(Exception Map)を選択
    """
    print(f"   [Auto Fill] エリア解析開始: {section_xpath}")
    
    # 1. まずエリア内のラジオボタンが表示されるまで待つ (スッポ抜け防止)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, f"{section_xpath}//input[@type='radio']"))
        )
    except:
        print("   [Info] このセクションにはラジオボタンが無いか、読み込みに失敗しました。スキップします。")
        return

    # 2. 全ラジオボタンを取得
    radios = driver.find_elements(By.XPATH, f"{section_xpath}//input[@type='radio']")
    if not radios:
        return

    # 3. nameごとにグループ化する
    radio_groups = {}
    for r in radios:
        name = r.get_attribute('name')
        if not name: continue
        if name not in radio_groups:
            radio_groups[name] = []
        radio_groups[name].append(r)

    print(f"   検出項目数: {len(radio_groups)}")

    # 4. グループごとに処理
    for name, elements in radio_groups.items():
        # 4-a. 既に選択されているかチェック (Safe Fill)
        is_already_selected = False
        for el in elements:
            if el.is_selected():
                is_already_selected = True
                break
        
        if is_already_selected:
            print(f"   [Skip] 既に選択済み: {name}")
            continue

        # 4-b. 選択すべきインデックスを決定
        target_index = EXCEPTION_INDEXES.get(name, 0)

        # 要素数チェック
        if target_index >= len(elements):
            print(f"   [Warn] {name} の選択肢不足 (要求:{target_index}, 実際:{len(elements)}) -> 左端を選択します")
            target_index = 0
        
        # 4-c. クリック実行
        try:
            target_el = elements[target_index]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_el)
            driver.execute_script("arguments[0].click();", target_el)
            print(f"   [Select] {name} -> Index:{target_index}")
        except Exception as e:
            print(f"   [Error] 選択失敗 {name}: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Tire Input Order) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        tire_data = data.get('tire_data', {})
        print(f"Target Plate: {data.get('plate')}")
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        MAX_RETRIES = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"   [Login] 接続試行中... ({attempt}/{MAX_RETRIES})")
                driver.get(target_url)
                id_parts = TMA_ID.split("-")
                input_strict(driver, "#cardNo1", id_parts[0])
                input_strict(driver, "#cardNo2", id_parts[1])
                input_strict(driver, "#password", TMA_PW)
                click_strict(driver, ".btn-primary")
                print("   [Login] 成功")
                break 
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e

        try: click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=5)
        except: pass 

        # [2] 点検開始
        print("\n--- [2] 点検開始 ---")
        try:
            click_strict(driver, "//span[@class='link-btn']/a[contains(text(), '点検')]")
            handle_popups(driver)
            wait_for_return_page(driver)
        except Exception as e:
            print(f"   [Error] 開始処理失敗: {e}")
            raise e

        # [2.5] 日常点検開始
        print("\n--- [2.5] 日常点検開始 ---")
        click_section_button(driver, "日常点検")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # [3] 入力: 日常点検 (セクションごとに一括処理)
        print("\n--- [3] 入力: 日常点検 ---")

        sections = [
            "engine", "tire", "motion", "in-car", 
            "equipment", "light", "perimeter", "trunk"
        ]

        for section_name in sections:
            print(f"   Processing Section: {section_name}")
            click_strict(driver, f"div[data-name='{section_name}']")
            
            # A. ラジオボタン処理
            fill_section_radios(driver, f"//div[@data-name='{section_name}']")

            # B. タイヤの数値入力 (タイヤタブが開いている今、実行する)
            if section_name == "tire":
                print("   Filling Tire Data (Depth/Pressure)...")
                wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
                for pos, suffix in wheels:
                    d = tire_data.get(pos, {})
                    # 製造週
                    input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
                    # 溝
                    depth_str = str(d.get('depth', '5.5'))
                    if '.' in depth_str: ip, fp = depth_str.split('.')
                    else: ip, fp = depth_str, '0'
                    input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
                    input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
                    # 空気圧
                    input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_section_radios(driver, "//body")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
