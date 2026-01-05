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
    """文字列からXPathかCSSセレクタか、単なるIDかを判定して返す"""
    if selector_str.startswith("/") or selector_str.startswith("("):
        return By.XPATH, selector_str
    
    # CSSセレクタとみなす条件
    if any(char in selector_str for char in ['#', '.', '[', ']', '>', ':']):
        return By.CSS_SELECTOR, selector_str
    
    # それ以外はIDとみなす
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

def click_section_button(driver, section_title):
    """IDがないボタン用: 指定されたセクション名（例: '日常点検'）を含む枠内の「点検」ボタンをクリックする"""
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    
    print(f"   [{section_title}] の開始ボタンを探しています...")
    try:
        click_strict(driver, xpath)
    except Exception as e:
        take_screenshot(driver, f"ERROR_SectionClick_{section_title}")
        raise Exception(f"「{section_title}」の開始ボタンが見つかりません。") from e

def handle_potential_popup(driver):
    """ボタン押下直後の「確認（よろしいですか？）」ポップアップを処理する"""
    try:
        confirm_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.ID, "posupMessageConfirmOk"))
        )
        print("   確認ポップアップを検知しました。「完了」ボタンを押します...")
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass # ポップアップが出なければ何もしない

def dismiss_success_modal(driver):
    """
    画面遷移後に出現する「完了しました」「一時保存しました」等の報告モーダルを閉じる
    IDがないボタンにも対応: <input value='閉じる'> を探す
    """
    try:
        # モーダル内の「閉じる」ボタンが表示されるのを少し待つ
        print("   完了報告モーダル（閉じるボタン）の確認中...")
        close_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@value='閉じる'] | //button[contains(text(), '閉じる')]"))
        )
        print("   完了報告モーダルを検知しました。「閉じる」をクリックします。")
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(1) # モーダルが消えるのを待つ
    except:
        print("   完了報告モーダルは表示されませんでした（または検知できませんでした）")

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

def select_all_radio_first_option(driver):
    """
    【車内清掃用】
    ページ内の全ラジオボタン項目を自動検出し、
    各グループで「OK (value='1')」または「最初の選択肢」を選択する
    """
    print("   ページ内の全ラジオボタン項目を自動検出・入力中...")
    try:
        # ページ内のラジオボタンのname属性をすべて取得（重複排除）
        radio_elements = driver.find_elements(By.XPATH, "//input[@type='radio']")
        names = set([el.get_attribute('name') for el in radio_elements if el.get_attribute('name')])
        
        print(f"   検出された項目数: {len(names)}")
        
        for name in names:
            target = None
            # まず value='1' (OK) を優先的に探す
            try:
                xpath_ok = f"//input[@name='{name}' and @value='1']"
                target = driver.find_element(By.XPATH, xpath_ok)
            except:
                # なければそのグループの最初のラジオボタンを選択 (左側)
                try:
                    xpath_any = f"(//input[@name='{name}'])[1]"
                    target = driver.find_element(By.XPATH, xpath_any)
                except:
                    pass
            
            if target:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                time.sleep(0.1)
                driver.execute_script("arguments[0].click();", target)
                print(f"   [Auto] Radio selected for: {name}")
            else:
                print(f"   [Warning] 項目 {name} の選択肢が見つかりませんでした")

    except Exception as e:
        print(f"   [Warning] ラジオボタン自動選択中にエラーが発生しましたが続行します: {e}")

def wait_for_return_page(driver):
    """工程終了後、一覧(search/index) または 点検トップ(maintenanceTop) に戻るのを待機"""
    print("   画面遷移を待機中(search/index/maintenanceTop)...")
    try:
        WebDriverWait(driver, 20).until(EC.url_matches(r"(search|index|maintenanceTop)"))
        time.sleep(2)
        print("   -> 画面遷移を確認しました")
    except:
        take_screenshot(driver, "ERROR_ReturnPage")
        raise Exception("期待する戻り画面(一覧または点検トップ)に遷移しませんでした")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Fix: Pure XPath Selectors) ===")

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
        click_strict(driver, ".btn-primary")
        
        # --- [1.5] メニュー回避 ---
        print("\n--- [1.5] メニュー画面遷移 ---")
        try:
             click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")
        except:
             pass 

        # --- [2] 車両リスト選択 & ポップアップ ---
        print("\n--- [2] 車両リスト選択 & 開始ポップアップ ---")
        try:
            # 1. 「点検」ボタンをクリック (IDなし対応)
            print("   「点検」ボタンを探しています...")
            inspection_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[@class='link-btn']/a[contains(text(), '点検')]"))
            )
            inspection_btn.click()
            print("   「点検」ボタンをクリックしました。")

            # 2. 確認ポップアップの処理
            handle_potential_popup(driver)

            # 画面遷移待機 (maintenanceTopへ)
            time.sleep(5)
            wait_for_return_page(driver)

        except Exception as e:
            print(f"   [Error] 車両選択/ポップアップ処理でエラー: {e}")
            take_screenshot(driver, "ERROR_Step2_InspectionClick")
            raise e

        # --- [2.5] トップ画面 (点検開始処理) ---
        print("\n--- [2.5] トップ画面 (点検開始) ---")
        click_section_button(driver, "日常点検")
        
        # --- [3] 日常点検入力 ---
        print("\n--- [3] 入力実行: 日常点検 ---")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # 1. エンジンルーム
        print("   [Step 1] エンジンルーム")
        click_strict(driver, "div[data-name='engine']") 
        
        select_radio_strict(driver, "coolantGauge", "2")
        select_radio_strict(driver, "engineOilGauge", "1")
        select_radio_strict(driver, "brakeFluidGauge", "1")
        select_radio_strict(driver, "washerFluidGauge", "2")

        # 2. タイヤ
        print("   [Step 2] タイヤ")
        click_strict(driver, "div[data-name='tire']")
        select_radio_strict(driver, "tireType", "1")
        
        # タイヤ損傷 (前後左右)
        select_radio_strict(driver, "tireDamageRightFront", "1")
        select_radio_strict(driver, "tireDamageLeftFront", "1")
        select_radio_strict(driver, "tireDamageLeftRear", "1")
        select_radio_strict(driver, "tireDamageRightRear", "1")

        wheels = [
            ('rf', 'FrontRightCm'), 
            ('lf', 'FrontLeftCm'), 
            ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')
        ]

        for pos, suffix in wheels:
            d = tire_data.get(pos, {})
            # 製造週
            input_strict(driver, f"input[name='tireMfr{suffix}']", d.get('week', ''))
            
            # 溝の深さ
            depth_str = str(d.get('depth', '5.5'))
            if '.' in depth_str:
                ip, fp = depth_str.split('.')
            else:
                ip, fp = depth_str, '0'
            input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
            input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
            
            # 空気圧 (調整前のみ入力)
            press = d.get('press', '')
            input_strict(driver, f"input[name='tirePressure{suffix}']", press)
            # input_strict(driver, f"input[name='tirePressureAdjusted{suffix}']", press) # スキップ

        # 3. 動作確認
        print("   [Step 3] 動作確認")
        click_strict(driver, "div[data-name='motion']")
        select_radio_strict(driver, "engineCondition", "1")
        select_radio_strict(driver, "brakeCondition", "1")
        select_radio_strict(driver, "parkingBrakeCondition", "1")
        select_radio_strict(driver, "washerSprayCondition", "1")
        select_radio_strict(driver, "wiperWipeCondition", "1")

        # 4. 車載品 - 運転席
        print("   [Step 4] 車載品 - 運転席")
        click_strict(driver, "div[data-name='in-car']")
        select_radio_strict(driver, "inspectionCertificateExist", "1")
        select_radio_strict(driver, "inspectionStickerExist", "1")
        select_radio_strict(driver, "autoLiabilityExist", "1")
        select_radio_strict(driver, "maintenanceStickerExist", "1")
        select_radio_strict(driver, "roomStickerExist", "1")
        select_radio_strict(driver, "deodorantsExist", "1")

        # 5. 装備確認
        print("   [Step 5] 装備確認")
        click_strict(driver, "div[data-name='equipment']")
        select_radio_strict(driver, "backMonitor", "1")
        select_radio_strict(driver, "cornerSensor", "1")
        select_radio_strict(driver, "brakeSupport", "1")
        select_radio_strict(driver, "laneDevianceAlert", "1")
        select_radio_strict(driver, "driveRecorder", "1")

        # 6. 灯火装置
        print("   [Step 6] 灯火装置")
        click_strict(driver, "div[data-name='light']")
        select_radio_strict(driver, "turnSignal", "1")
        
        # 7. 車両周り他
        print("   [Step 7] 車両周り他")
        click_strict(driver, "div[data-name='perimeter']")
        select_radio_strict(driver, "fuelCap", "1")
        select_radio_strict(driver, "carStickerExist", "1")

        # 8. 車載品 - トランク
        print("   [Step 8] 車載品 - トランク")
        click_strict(driver, "div[data-name='trunk']")
        select_radio_strict(driver, "warningTrianglePlateDamage", "1")
        select_radio_strict(driver, "puncRepairKitExist", "1")
        select_radio_strict(driver, "cleaningKit", "1")

        # 一時保存 (すべてXPathで記述して混在を解消)
        print("   一時保存をクリック...")
        # ボタンの文字、inputのname属性、class属性をXPathですべて網羅
        temp_save_xpath = "//input[@value='一時保存'] | //a[contains(text(), '一時保存')] | //input[@name='doOnceTemporary'] | //*[contains(@class, 'is-break')]"
        click_strict(driver, temp_save_xpath)
        
        handle_potential_popup(driver) # 確認ダイアログ処理
        wait_for_return_page(driver)   # 画面遷移待ち
        dismiss_success_modal(driver)  # 完了報告モーダルを閉じる

        
        # --- [4] 車内清掃フェーズ ---
        print("\n--- [4] 車内清掃フェーズ ---")
        click_section_button(driver, "車内清掃")

        # 全項目自動選択
        select_all_radio_first_option(driver)

        # 完了ボタン (すべてXPathで記述して混在を解消)
        print("   完了ボタンをクリック...")
        complete_btn_xpath = "//input[@value='完了'] | //a[contains(text(), '完了')] | //*[contains(@class, 'complete-button')] | //*[contains(@class, 'is-complete')]"
        click_strict(driver, complete_btn_xpath)
        
        handle_potential_popup(driver)
        wait_for_return_page(driver)
        dismiss_success_modal(driver)

        # --- [5] 洗車フェーズ ---
        print("\n--- [5] 洗車フェーズ ---")
        click_section_button(driver, "洗車")

        select_radio_strict(driver, "exteriorDirt", "2") # 洗車不要

        print("   完了ボタンをクリック...")
        click_strict(driver, complete_btn_xpath)
        
        handle_potential_popup(driver)
        wait_for_return_page(driver)
        dismiss_success_modal(driver)

        # --- [6] 外装確認フェーズ ---
        print("\n--- [6] 外装確認フェーズ ---")
        click_section_button(driver, "外装確認")

        select_radio_strict(driver, "exteriorState", "1")

        print("   完了ボタンをクリック...")
        click_strict(driver, complete_btn_xpath)
        
        handle_potential_popup(driver)
        wait_for_return_page(driver)
        dismiss_success_modal(driver)

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
