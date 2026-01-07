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
# 厳格な操作関数群 (Timeout Extended)
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
    """汎用クリック関数 (Timeout: 30s)"""
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
    """
    メイン操作ボタン（一時保存/完了）をクリックする。
    隠れているポップアップ(alert-modal)内のボタンは除外する。
    Timeout: 30s
    """
    if button_type == "save":
        label = "一時保存"
        base_xpath = "(//input[contains(@class,'is-break')] | //input[@name='doOnceTemporary'] | //input[@value='一時保存'] | //a[contains(text(),'一時保存')])"
    else:
        label = "完了"
        base_xpath = "(//input[contains(@class,'complete-button')] | //input[@name='doOnceSave'] | //input[@value='完了'] | //a[contains(text(),'完了')])"

    # ポップアップ内の要素を除外
    xpath = f"{base_xpath}[not(ancestor::div[contains(@class, 'alert-modal')])]"

    print(f"   画面上の「{label}」ボタン（ポップアップ外）を探しています...")
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
    """ボタン押下後のポップアップ処理セット"""
    # 1. 確認ダイアログ
    try:
        confirm_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        print("   確認ポップアップ検知 -> 「完了」をクリック")
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass 

    # 2. 完了報告モーダル
    try:
        close_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"))
        )
        print("   完了報告モーダル検知 -> 「閉じる」をクリック")
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1)
    except:
        pass 

def input_strict(driver, selector_str, value):
    """入力関数 (Timeout: 30s)"""
    by_method = By.XPATH if selector_str.startswith("/") else By.CSS_SELECTOR
    try:
        el = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((by_method, selector_str)))
        el.clear()
        el.send_keys(str(value))
        print(f"   [OK] Input: {value} -> {selector_str}")
    except Exception as e:
        take_screenshot(driver, "ERROR_InputFailed")
        raise Exception(f"入力失敗 (Timeout): {selector_str}") from e

def select_radio_strict(driver, name_attr, value):
    """ラジオボタン選択 (Timeout: 30s)"""
    xpath = f"//input[@name='{name_attr}' and @value='{value}']"
    try:
        el = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, xpath)))
        driver.execute_script("arguments[0].click();", el)
        print(f"   [OK] Radio: {name_attr}={value}")
    except Exception as e:
        take_screenshot(driver, f"ERROR_Radio_{name_attr}")
        raise Exception(f"ラジオボタン選択失敗: {name_attr}={value}") from e

def select_all_radio_first_option(driver):
    """全ラジオボタン自動選択"""
    print("   全ラジオボタン項目の自動選択を開始...")
    try:
        radios = driver.find_elements(By.XPATH, "//input[@type='radio']")
        names = set([el.get_attribute('name') for el in radios if el.get_attribute('name')])
        
        print(f"   検出項目数: {len(names)}")
        
        for name in names:
            target_xpath = f"//input[@name='{name}' and @value='1'] | (//input[@name='{name}'])[1]"
            try:
                target = driver.find_element(By.XPATH, target_xpath)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                driver.execute_script("arguments[0].click();", target)
                print(f"   [Auto] Selected for: {name}")
            except:
                pass
    except Exception as e:
        print(f"   [Warning] 自動選択エラー: {e}")

def wait_for_return_page(driver):
    """画面遷移待機 (Timeout: 40s)"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 遷移確認完了")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("トップ画面に戻れませんでした (Timeout)")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Login Retry Added) ===")

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
        # [1] ログイン (リトライ機能追加版)
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
                break # ログイン成功でループを抜ける
            except Exception as e:
                print(f"   [Login Error] ログイン失敗: {e}")
                if attempt < MAX_RETRIES:
                    print("   [Retry] 10秒待機後に再試行します...")
                    time.sleep(10)
                else:
                    print("   [Fatal] リトライ上限に達しました。")
                    take_screenshot(driver, "LOGIN_FAILED_FINAL")
                    raise e # 最終的なエラーとして処理を中断

        
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
        
        # [3] 日常点検入力
        print("\n--- [3] 入力: 日常点検 ---")
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # エンジン
        click_strict(driver, "div[data-name='engine']") 
        select_radio_strict(driver, "coolantGauge", "2")
        select_radio_strict(driver, "engineOilGauge", "1")
        select_radio_strict(driver, "brakeFluidGauge", "1")
        select_radio_strict(driver, "washerFluidGauge", "2")

        # タイヤ
        click_strict(driver, "div[data-name='tire']")
        select_radio_strict(driver, "tireType", "1")
        select_radio_strict(driver, "tireDamageRightFront", "1")
        select_radio_strict(driver, "tireDamageLeftFront", "1")
        select_radio_strict(driver, "tireDamageLeftRear", "1")
        select_radio_strict(driver, "tireDamageRightRear", "1")

        wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
        for pos, suffix in wheels:
            d = tire_data.get(pos, {})
            input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
            
            depth_str = str(d.get('depth', '5.5'))
            if '.' in depth_str: ip, fp = depth_str.split('.')
            else: ip, fp = depth_str, '0'
            input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
            input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
            
            # 空気圧
            input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # 動作確認
        click_strict(driver, "div[data-name='motion']")
        select_radio_strict(driver, "engineCondition", "1")
        select_radio_strict(driver, "brakeCondition", "1")
        select_radio_strict(driver, "parkingBrakeCondition", "1")
        select_radio_strict(driver, "washerSprayCondition", "1")
        select_radio_strict(driver, "wiperWipeCondition", "1")

        # 車載品
        click_strict(driver, "div[data-name='in-car']")
        select_radio_strict(driver, "inspectionCertificateExist", "1")
        select_radio_strict(driver, "inspectionStickerExist", "1")
        select_radio_strict(driver, "autoLiabilityExist", "1")
        select_radio_strict(driver, "maintenanceStickerExist", "1")
        select_radio_strict(driver, "roomStickerExist", "1")
        select_radio_strict(driver, "deodorantsExist", "1")

        # 装備
        click_strict(driver, "div[data-name='equipment']")
        select_radio_strict(driver, "backMonitor", "1")
        select_radio_strict(driver, "cornerSensor", "1")
        select_radio_strict(driver, "brakeSupport", "1")
        select_radio_strict(driver, "laneDevianceAlert", "1")
        select_radio_strict(driver, "driveRecorder", "1")

        # 灯火
        click_strict(driver, "div[data-name='light']")
        select_radio_strict(driver, "turnSignal", "1")
        
        # 車両周り
        click_strict(driver, "div[data-name='perimeter']")
        select_radio_strict(driver, "fuelCap", "1")
        select_radio_strict(driver, "carStickerExist", "1")

        # トランク
        click_strict(driver, "div[data-name='trunk']")
        select_radio_strict(driver, "warningTrianglePlateDamage", "1")
        select_radio_strict(driver, "puncRepairKitExist", "1")
        select_radio_strict(driver, "cleaningKit", "1")

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        select_all_radio_first_option(driver)
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        select_radio_strict(driver, "exteriorDirt", "2")
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        select_radio_strict(driver, "exteriorState", "1")
        
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
