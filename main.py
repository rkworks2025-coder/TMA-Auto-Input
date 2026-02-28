import sys
import os
import time
import datetime
import json
import urllib.request
import urllib.parse
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
# ★ダミーテスト環境のURLに変更済み
DEFAULT_LOGIN_URL = "https://rkworks2025-coder.github.io/TMA-Simulation-Lab/login"
TMA_ID = "0030-927583"
TMA_PW = "Ccj-222223"
EVIDENCE_DIR = "evidence"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1474006170057441300/Emo5Ooe48jBUzMhzLrCBn85_3Td-ck3jYtXtVa2vdXWWyT2HxSuKghWchrG7gCsZhEqY"
GAS_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

# ==========================================
# 例外設定（位置指定: 0始まり）
# ==========================================
EXCEPTION_INDEXES = {
    # ウォッシャー液: 2番目 "OK(補充)"
    "washerFluidGauge": 1,
    # 洗車の汚れ: 2番目 "洗車不要"
    "exteriorDirt": 1
}

# ==========================================
# スキップ設定（自動入力をしない項目）
# ==========================================
SKIP_NAMES = [
    "tireJackupSetExist",  # 車載工具類・ジャッキ
    "juniorSeat"           # ジュニアシート
]

# ==========================================
# 厳格な操作関数群 
# (Timeout Extended)
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

# ==========================================
# 新・自動入力ロジック (HTML構造対応 & Skip機能)
# ==========================================
def fill_active_tab_radios(driver):
    """
    現在表示されている入力エリアを探し、その中のラジオボタンを自動処理する。
    1. div.tab-contents (日常点検用) があればそれを使う。
    2. なければ body 全体 (車内清掃など) を使う。
    3. SKIP_NAMES に含まれる項目は無視する。
    """
    print("   [Auto Fill] 表示中の項目を解析中...")
    time.sleep(0.5) # 切り替えアニメーション待機
    
    # 1. 日常点検用のタブコンテンツを探す
    target_area = None
    try:
        # 非表示も含めて取得し、is_displayedで判定
        contents = driver.find_elements(By.CSS_SELECTOR, "div.tab-contents")
        for c in contents:
            if c.is_displayed():
                target_area = c
                break
    except:
        pass

    # 2. タブが見つからない場合は全体(body)を対象にする
    if not target_area:
        target_area = driver.find_element(By.TAG_NAME, "body")

    try:
        # 3. エリア内のラジオボタンを収集
        radios = target_area.find_elements(By.TAG_NAME, "input")
        radios = [r for r in radios if r.get_attribute("type") == "radio"]

        if not radios:
            print("   [Info] 操作可能なラジオボタンがありませんでした。")
            return

        # 4. nameごとにグループ化
        radio_groups = {}
        for r in radios:
            name = r.get_attribute("name")
            if not name: continue
            if name not in radio_groups:
                radio_groups[name] = []
            radio_groups[name].append(r)
        
        print(f"   検出項目数: {len(radio_groups)}")

        # 5. グループごとに処理
        for name, elements in radio_groups.items():
            # (Skip Check) 除外リストに含まれる場合はスキップ
            if name in SKIP_NAMES:
                print(f"   [Skip] 除外リスト対象: {name}")
                continue

            # (Safe Fill) 既にチェックが入っているか確認
            is_checked = False
            for el in elements:
                if el.is_selected():
                    is_checked = True
                    break
            
            if is_checked:
                continue # 既に値が入っている場合はスキップ

            # 選択するインデックス (デフォルト0=左端, 例外は指定値)
            target_index = EXCEPTION_INDEXES.get(name, 0)
            
            # 要素数が足りているか確認してクリック
            if target_index < len(elements):
                # クリック実行 (オーバーレイ対策でJSクリックを使用)
                driver.execute_script("arguments[0].click();", elements[target_index])
                print(f"   [Select] {name} -> Index:{target_index}")
            else:
                # 選択肢が足りない場合は安全のため左端(0)を選択
                if len(elements) > 0:
                    driver.execute_script("arguments[0].click();", elements[0])
                    print(f"   [Select(Fallback)] {name} -> Index:0")

    except Exception as e:
        print(f"   [Error] 自動入力中にエラー: {e}")

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

def send_discord_notification(message):
    """Discordへ通知を送信する"""
    try:
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=json.dumps({"content": message}).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"  # 403回避用
            },
            method="POST"
        )
        with urllib.request.urlopen(req):
            pass
    except Exception as e:
        print(f"   [Error] Discord通知に失敗しました: {e}")

# ==========================================
# メイン処理
# ==========================================
def main():
    print("=== Automation Start (Integrated GAS Pull & Cookie & Zero Fill) ===")

    if len(sys.argv) < 2:
        print("Error: No payload provided.")
        sys.exit(1)
    
    try:
        payload_str = sys.argv[1]
        data = json.loads(payload_str)
        target_url = data.get('target_url') or DEFAULT_LOGIN_URL
        plate = data.get('plate')
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    if not plate:
        print("Error: No plate provided in payload.")
        sys.exit(1)

    print(f"Target Plate: {plate}")

    # [0] GASからタイヤデータとCookieを取得
    print("\n--- [0] GASデータ Pull ---")
    try:
        req_url = f"{GAS_URL}?action=getTireData&plate={urllib.parse.quote(plate)}"
        req = urllib.request.Request(req_url)
        with urllib.request.urlopen(req) as res:
            gas_res = json.loads(res.read().decode('utf-8'))
    except Exception as e:
        send_discord_notification(f"[{plate}] GASからのデータ取得に失敗しました: {e}")
        sys.exit(1)

    if not gas_res.get("ok"):
        err_msg = gas_res.get("error", "Unknown error")
        print(f"GAS Error: {err_msg}")
        if err_msg == "no_recent_tire_data":
            send_discord_notification(f"[{plate}] 24時間以内のタイヤ点検データが存在しないため、自動入力を中止しました。")
        else:
            send_discord_notification(f"[{plate}] GASエラーのため自動入力を中止しました: {err_msg}")
        sys.exit(1)

    tire_data = gas_res.get("tire_data", {})
    saved_cookie_str = gas_res.get("cookie", "")
    print("   [OK] データ取得完了")

    print("   ▼▼▼ 取得したタイヤデータ詳細 ▼▼▼")
    print(json.dumps(tire_data, indent=2, ensure_ascii=False))
    print("   ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲")

    driver = get_chrome_driver()

    try:
        # [1] ログイン
        print("\n--- [1] ログイン ---")
        driver.get(target_url)
        
        login_success = False

        if saved_cookie_str:
            print("   保存されたCookieを使ってログインを試行します...")
            try:
                cookies = json.loads(saved_cookie_str)
                for c in cookies:
                    driver.add_cookie(c)
                
                # Cookie適用のためリロード（ダッシュボード確認）
                driver.get("https://dailycheck.tc-extsys.jp/tcrappsweb/web/menu/tawMenu.html")
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")))
                print("   [OK] Cookieでのログインに成功しました（スキップ完了）")
                login_success = True
            except:
                print("   [Info] Cookieログイン失敗（期限切れ等）。通常ログインへ移行します。")
                driver.get(target_url)

        if not login_success:
            id_parts = TMA_ID.split("-")
            input_strict(driver, "#cardNo1", id_parts[0])
            input_strict(driver, "#cardNo2", id_parts[1])
            input_strict(driver, "#password", TMA_PW)
            click_strict(driver, ".btn-primary")
            
            try: 
                click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=10)
            except: 
                pass 

            # 新しいCookieを取得してGASへPush
            try:
                new_cookies = driver.get_cookies()
                new_cookie_str = json.dumps(new_cookies)
                req_data = json.dumps({"action": "updateCookie", "cookie": new_cookie_str}).encode('utf-8')
                req = urllib.request.Request(
                    GAS_URL,
                    data=req_data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req):
                    print("   [OK] 新しいCookieをGASへ保存しました")
            except Exception as e:
                print(f"   [Warn] CookieのGAS保存に失敗: {e}")

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

        # エンジン (タブ切り替えは元のまま、入力のみ自動化)
        click_strict(driver, "div[data-name='engine']") 
        fill_active_tab_radios(driver)

        # タイヤ
        click_strict(driver, "div[data-name='tire']")
        fill_active_tab_radios(driver)

        wheels = [('rf', 'FrontRightCm'), ('lf', 'FrontLeftCm'), ('lr', 'RearLeftBi4'), ('rr', 'RearRightBi4')]
        for pos, suffix in wheels:
            d = tire_data.get(pos, {})
            
            # ★製造年週の4桁補完（0埋め）
            week_raw = d.get('week', '')
            week_val = str(week_raw).zfill(4) if week_raw else ""
            input_strict(driver, f"input[name='tireMfr{suffix}']", week_val)
            
            depth_str = str(d.get('depth', '5.5'))
            if '.' in depth_str: ip, fp = depth_str.split('.')
            else: ip, fp = depth_str, '0'
            input_strict(driver, f"input[name='tireGroove{suffix}Ip']", ip)
            input_strict(driver, f"input[name='tireGroove{suffix}Fp']", fp)
            
            # 空気圧
            input_strict(driver, f"input[name='tirePressure{suffix}']", d.get('press', ''))

        # 動作確認
        click_strict(driver, "div[data-name='motion']")
        fill_active_tab_radios(driver)

        # 車載品
        click_strict(driver, "div[data-name='in-car']")
        fill_active_tab_radios(driver)

        # 装備
        click_strict(driver, "div[data-name='equipment']")
        fill_active_tab_radios(driver)

        # 灯火
        click_strict(driver, "div[data-name='light']")
        fill_active_tab_radios(driver)
        
        # 車両周り
        click_strict(driver, "div[data-name='perimeter']")
        fill_active_tab_radios(driver)

        # トランク
        click_strict(driver, "div[data-name='trunk']")
        fill_active_tab_radios(driver)

        # === 一時保存 ===
        print("   一時保存をクリック...")
        click_main_action_button(driver, "save")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_active_tab_radios(driver)
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [5] 洗車
        print("\n--- [5] 洗車 ---")
        click_section_button(driver, "洗車")
        fill_active_tab_radios(driver)
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_active_tab_radios(driver)
        
        click_main_action_button(driver, "complete")
        handle_popups(driver)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        send_discord_notification(f"[{plate}] TMAへの入力が完了しました")
        sys.exit(0)

    except Exception as e:
        print(f"\n[!!!] CRITICAL ERROR [!!!]\n{e}")
        take_screenshot(driver, "FATAL_ERROR")
        send_discord_notification(f"[{plate}] エラーにより入力が完了しませんでした: {e}")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
