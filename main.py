import sys
import os
import re
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
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# 設定エリア
# ==========================================
DEFAULT_LOGIN_URL = "https://dailycheck.tc-extsys.jp/tcrappsweb/web/login/tawLogin.html"
TMA_ID = os.environ.get("TMA_ID", "")
TMA_PW = os.environ.get("TMA_PW_MODE1", "")
EVIDENCE_DIR = "evidence"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
GAS_URL = "https://script.google.com/macros/s/AKfycbyXbPaarnD7mQa_rqm6mk-Os3XBH6C731aGxk7ecJC5U3XjtwfMkeF429rezkAo79jN/exec"

# ==========================================
# ★サーバー遅延対策 (2026-10-26)
# ==========================================
# ローディングの幕（これが残っている間にクリックすると element click intercepted になる）
LOADING_OVERLAY_CSS = ".loading-view, .loading-view-bg"
OVERLAY_WAIT = 60            # ローディングの幕が消えるまでの上限(秒)
TAB_CONTENT_WAIT = 30        # タブ切替後、そのタブの入力項目が表示されるまでの上限(秒)
TAB_ALREADY_OPEN_WAIT = 5    # 最初に開くタブが既に表示中かどうかを見極める時間(秒)
RADIO_WAIT = 10              # 表示されたエリアにラジオボタンが出るまでの上限(秒)
LAYOUT_WAIT = 30             # 任意タブ/任意セクションの有無を判定する前に、画面の骨組みが出るまでの上限(秒)
AFTER_ACTION_WAIT = 60       # ボタン押下後、ポップアップ処理と画面遷移が終わるまでの上限(秒)
LOGIN_MAX_ATTEMPTS = 2       # ログインの試行回数
RETURN_URL_PATTERN = r"(search|index|maintenanceTop)"

# 入力項目が見つからなかったタブ/セクション（最後のDiscord通知に添える）
EMPTY_AREAS = []

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
    "juniorSeat",          # ジュニアシート
    "turnSignal"           # 灯火装置：点灯状態（基本点検時の意図的未入力 → 一時保存ボタン維持用）
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

def wait_overlay_gone(driver, timeout=OVERLAY_WAIT):
    """★ローディングの幕が画面から消えるまで待つ（消えなければ警告のみで続行）"""
    def _gone(d):
        try:
            for el in d.find_elements(By.CSS_SELECTOR, LOADING_OVERLAY_CSS):
                if el.is_displayed():
                    return False
            return True
        except StaleElementReferenceException:
            return False
    try:
        WebDriverWait(driver, timeout, poll_frequency=0.3).until(_gone)
    except TimeoutException:
        print(f"   [注意] ローディング表示が{timeout}秒以内に消えませんでした。続行します。")

def _wait_and_click(driver, by_method, selector_str, timeout):
    """★ローディングの幕が消えるのを待ってからクリックする。
    幕に遮られた(element click intercepted)場合は、幕が消えるのを待って押し直す。
    遮られたクリックは画面に届いていないため、押し直しても二重操作にはならない。"""
    deadline = time.time() + timeout
    while True:
        wait_overlay_gone(driver)
        remaining = max(1, deadline - time.time())
        el = WebDriverWait(driver, remaining).until(EC.element_to_be_clickable((by_method, selector_str)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        wait_overlay_gone(driver)
        try:
            el.click()
            return
        except (ElementClickInterceptedException, StaleElementReferenceException):
            if time.time() > deadline:
                raise
            print("   [注意] クリックがローディング表示に遮られたため、表示が消えるのを待って押し直します。")
            time.sleep(1)

def click_strict(driver, selector_str, timeout=30):
    """汎用クリック関数 (Timeout: 30s)"""
    by_method = By.XPATH if selector_str.startswith("/") or selector_str.startswith("(") else By.CSS_SELECTOR
    try:
        _wait_and_click(driver, by_method, selector_str, timeout)
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
        _wait_and_click(driver, By.XPATH, xpath, 30)
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

def wait_tab_bar(driver):
    """★日常点検のタブ（タイヤタブは全点検共通で必ずある）が描画されるまで待つ。
    これを待たずに任意タブの有無を5秒で判定すると、描画が遅いだけなのに
    「タブ無し＝基本点検」と誤判定して入力を飛ばしてしまうため。"""
    try:
        WebDriverWait(driver, LAYOUT_WAIT).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-name='tire']")))
    except TimeoutException:
        take_screenshot(driver, "ERROR_TabBarNotLoaded")
        raise Exception(f"日常点検の入力画面が{LAYOUT_WAIT}秒以内に表示されませんでした。")
    wait_overlay_gone(driver)

def click_tab_if_exists(driver, selector_str, timeout=5):
    """
    タブが存在・表示されていればクリックしてTrueを返す。
    存在しない・非表示の場合はスキップしてFalseを返す。
    基本点検時に存在しないタブを安全に読み飛ばすために使用。
    ★呼び出し前に wait_tab_bar() で画面の描画完了を確認しておくこと。
    """
    try:
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector_str)))
    except:
        print(f"   [Skip] タブ非表示/不存在のためスキップ: {selector_str}")
        return False
    _wait_and_click(driver, By.CSS_SELECTOR, selector_str, 30)
    print(f"   [OK] Tab Click: {selector_str}")
    return True

def click_section_if_exists(driver, section_title, timeout=5):
    """
    セクションの開始ボタンが存在すればクリックしてTrueを返す。
    存在しない場合はスキップしてFalseを返す。
    基本点検時に存在しないセクション（洗車など）を安全に読み飛ばすために使用。
    ★描画が遅いだけで「無し」と誤判定しないよう、先にセクション一覧の描画を待つ。
    """
    xpath = f"//div[contains(@class, 'check-state-area')][.//p[contains(text(), '{section_title}')]]//a[contains(text(), '点検')]"
    print(f"   [{section_title}] の開始ボタンを探しています（存在確認）...")
    try:
        WebDriverWait(driver, LAYOUT_WAIT).until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'check-state-area')]")))
    except TimeoutException:
        take_screenshot(driver, "ERROR_SectionListNotLoaded")
        raise Exception(f"点検セクション一覧が{LAYOUT_WAIT}秒以内に表示されませんでした。")
    wait_overlay_gone(driver)
    try:
        WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    except:
        print(f"   [Skip] セクション不存在のためスキップ: {section_title}")
        return False
    _wait_and_click(driver, By.XPATH, xpath, 30)
    print(f"   [OK] Section Click: {section_title}")
    return True

def handle_popups(driver, start_url=None, timeout=AFTER_ACTION_WAIT):
    """ボタン押下後のポップアップ処理セット
    ★サーバー遅延対策: 固定の5秒/8秒待ちをやめ、
    「確認ダイアログ」「完了報告モーダル」「画面遷移」のどれかが起きるまで最大timeout秒待ち、
    出たものから順に処理する。画面遷移後も少しの間は完了報告モーダルの出現を見張る。"""
    modal_xpath = "//div[contains(@class,'alert-modal')]//input[@value='閉じる'] | //div[contains(@class,'alert-modal')]//button[contains(text(),'閉じる')]"
    end = time.time() + timeout
    left_at = None
    while time.time() < end:
        try:
            # 1. 確認ダイアログ
            confirm = [b for b in driver.find_elements(By.ID, "posupMessageConfirmOk") if b.is_displayed()]
            if confirm:
                print("   確認ポップアップ検知 -> 「完了」をクリック")
                driver.execute_script("arguments[0].click();", confirm[0])
                time.sleep(1)
                continue

            # 2. 完了報告モーダル
            close = [b for b in driver.find_elements(By.XPATH, modal_xpath) if b.is_displayed()]
            if close:
                print("   完了報告モーダル検知 -> 「閉じる」をクリック")
                driver.execute_script("arguments[0].click();", close[0])
                time.sleep(1)
                continue

            # 3. 画面遷移（元の画面から移り、戻り先の画面になった）
            cur = driver.current_url
            if (start_url is None or cur != start_url) and re.search(RETURN_URL_PATTERN, cur):
                if left_at is None:
                    left_at = time.time()
                elif time.time() - left_at >= 3:
                    # 遷移後3秒間モーダルが出なければ処理完了とみなす
                    return
        except StaleElementReferenceException:
            pass
        time.sleep(0.3)
    print(f"   [注意] ボタン押下後{timeout}秒以内に画面遷移を確認できませんでした。")

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
def get_displayed_tab_content(driver):
    """★現在表示されている日常点検のタブコンテンツ(div.tab-contents)を返す（無ければNone）"""
    try:
        for c in driver.find_elements(By.CSS_SELECTOR, "div.tab-contents"):
            if c.is_displayed():
                return c
    except StaleElementReferenceException:
        pass
    return None

def open_tab(driver, selector_str, optional=False, may_be_current=False):
    """★日常点検のタブを開き、そのタブの中身に切り替わるまで待つ。
    クリック前に表示されていたタブコンテンツを覚えておき、別のものに切り替わったことを確認してから返す。
    （以前はクリック後0.5秒で読み取っていたため、描画が遅いと前のタブを読んだり項目無しになったりして、
      入力漏れのまま一時保存されていた）
    optional=True の場合、タブが存在しなければFalseを返す（基本点検時に存在しないタブ用）。
    may_be_current=True は最初に開くタブ用。画面を開いた時点で既にそのタブが表示されている場合は
    中身が切り替わらないため、短時間（TAB_ALREADY_OPEN_WAIT秒）切替が無ければ表示中のものをそのまま使う。"""
    before = get_displayed_tab_content(driver)
    if optional:
        if not click_tab_if_exists(driver, selector_str):
            return False
    else:
        click_strict(driver, selector_str)

    def _switched(d):
        cur = get_displayed_tab_content(d)
        if cur is None:
            return False
        if before is not None and cur == before:
            return False
        return True
    try:
        WebDriverWait(driver, TAB_ALREADY_OPEN_WAIT if (may_be_current and before is not None) else TAB_CONTENT_WAIT,
                      poll_frequency=0.3).until(_switched)
    except TimeoutException:
        if may_be_current and before is not None and get_displayed_tab_content(driver) == before:
            print(f"   [Info] タブ {selector_str} は最初から表示中のため、そのまま入力します。")
            wait_overlay_gone(driver)
            return True
        take_screenshot(driver, "ERROR_TabNotSwitched")
        raise Exception(f"タブ {selector_str} の入力項目が{TAB_CONTENT_WAIT}秒以内に表示されませんでした（入力漏れ防止のため中止）")
    wait_overlay_gone(driver)
    return True

def fill_active_tab_radios(driver, area_label=""):
    """
    現在表示されている入力エリアを探し、その中のラジオボタンを自動処理する。
    1. div.tab-contents (日常点検用) があればそれを使う。
    2. なければ body 全体 (車内清掃など) を使う。
    3. SKIP_NAMES に含まれる項目は無視する。
    ★サーバー遅延対策: 固定0.5秒待ちをやめ、ローディング表示が消え、
      ラジオボタンが出るまで最大RADIO_WAIT秒待つ。出なければ記録して最後に通知する。
    """
    print("   [Auto Fill] 表示中の項目を解析中...")
    wait_overlay_gone(driver)

    def _find_area_and_radios(d):
        # 1. 日常点検用のタブコンテンツを探す
        area = get_displayed_tab_content(d)
        # 2. タブが見つからない場合は全体(body)を対象にする
        if not area:
            area = d.find_element(By.TAG_NAME, "body")
        # 3. エリア内のラジオボタンを収集
        rs = [r for r in area.find_elements(By.TAG_NAME, "input") if r.get_attribute("type") == "radio"]
        return (area, rs) if rs else False

    radios = []
    try:
        _, radios = WebDriverWait(driver, RADIO_WAIT, poll_frequency=0.3,
                                  ignored_exceptions=(StaleElementReferenceException,)).until(_find_area_and_radios)
    except TimeoutException:
        print(f"   [注意] 操作可能なラジオボタンが{RADIO_WAIT}秒待っても見つかりませんでした: {area_label}")
        EMPTY_AREAS.append(area_label or "不明なエリア")
        return

    try:
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
        # ★入力途中のエラーは握りつぶさず中止する（入力漏れのまま保存しないため）
        take_screenshot(driver, "ERROR_AutoFill")
        raise Exception(f"自動入力中にエラー（{area_label}）: {e}") from e

def wait_for_return_page(driver):
    """画面遷移待機 (Timeout: 40s)"""
    print("   トップ画面への遷移待機中...")
    try:
        WebDriverWait(driver, 40).until(EC.url_matches(RETURN_URL_PATTERN))
        wait_overlay_gone(driver)
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

def login_with_password(driver, target_url):
    """★ID/PWでログインし、ログイン画面から抜けたことを確認する（失敗時は10秒あけて1回やり直す）"""
    last_err = None
    for attempt in range(1, LOGIN_MAX_ATTEMPTS + 1):
        try:
            if attempt > 1:
                driver.get(target_url)
            id_parts = TMA_ID.split("-")
            input_strict(driver, "#cardNo1", id_parts[0])
            input_strict(driver, "#cardNo2", id_parts[1])
            input_strict(driver, "#password", TMA_PW)
            click_strict(driver, ".btn-primary")
            WebDriverWait(driver, 30).until(lambda d: "login" not in d.current_url.lower())
            print("   [OK] ログインに成功しました")
            return
        except Exception as e:
            last_err = e
            print(f"   [注意] ログイン失敗 {attempt}/{LOGIN_MAX_ATTEMPTS}: {str(e).splitlines()[0][:100] if str(e) else type(e).__name__}")
            if attempt < LOGIN_MAX_ATTEMPTS:
                time.sleep(10)
    take_screenshot(driver, "ERROR_LoginFailed")
    raise Exception("TMAへのログインに失敗しました（PASSが正しくない可能性があります）") from last_err

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
        # 巡回アプリの「TMAボタン」押下時、GAS(Tirelog側)がその場でTirelogを直接
        # スキャンして見つけた最新データを、GitHub Actionsのpayloadに埋め込んで渡してくる。
        # これが存在する場合はそれを信頼できる最新データとしてそのまま使う。
        embedded_tire_data = data.get('tire_data')
    except Exception as e:
        print(f"Error parsing payload: {e}")
        sys.exit(1)

    if not plate:
        print("Error: No plate provided in payload.")
        sys.exit(1)

    print(f"Target Plate: {plate}")

    # [0] GASからCookieを取得（タイヤデータは可能な限りpayload埋め込み分を使用）
    print("\n--- [0] GAS Cookie Pull ---")
    GAS_RETRY_COUNT = 3
    GAS_RETRY_INTERVAL = 10  # 秒
    gas_res = None
    for attempt in range(1, GAS_RETRY_COUNT + 1):
        try:
            req_url = f"{GAS_URL}?action=getTireData&plate={urllib.parse.quote(plate)}"
            req = urllib.request.Request(req_url)
            with urllib.request.urlopen(req) as res:
                gas_res = json.loads(res.read().decode('utf-8'))
            print(f"   [OK] GAS通信成功 (試行 {attempt}/{GAS_RETRY_COUNT})")
            break
        except Exception as e:
            print(f"   [Warn] GAS通信失敗 (試行 {attempt}/{GAS_RETRY_COUNT}): {e}")
            if attempt < GAS_RETRY_COUNT:
                print(f"   {GAS_RETRY_INTERVAL}秒後にリトライします...")
                time.sleep(GAS_RETRY_INTERVAL)
            else:
                print("   [Warn] GAS(Cookie取得)への通信に失敗しましたが、通常ログインで継続します。")

    tire_data = embedded_tire_data
    saved_cookie_str = ""

    if gas_res and gas_res.get("ok"):
        # Cookieは取得できる場合のみ利用（無くても通常ログインにフォールバックする）
        saved_cookie_str = gas_res.get("cookie", "")
        if tire_data is None:
            tire_data = gas_res.get("tire_data", {})
    elif tire_data is None:
        # payloadにも埋め込みデータが無く(workflow_dispatchの手動実行等)、
        # 別GASへの照会も失敗/エラーだった場合のみ、ここで初めて中止する
        err_msg = (gas_res.get("error") if gas_res else "GAS通信失敗") or "Unknown error"
        print(f"GAS Error: {err_msg}")
        if err_msg == "no_recent_tire_data":
            send_discord_notification(f"[{plate}] 24時間以内のタイヤ点検データが存在しないため、自動入力を中止しました。")
        else:
            send_discord_notification(f"[{plate}] GASエラーのため自動入力を中止しました: {err_msg}")
        sys.exit(1)

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
                # ★サーバー遅延対策: 確認待ちを5秒→15秒に延長（遅いだけで通常ログインに落ちないように）
                driver.get("https://dailycheck.tc-extsys.jp/tcrappsweb/web/menu/tawMenu.html")
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]")))
                print("   [OK] Cookieでのログインに成功しました（スキップ完了）")
                login_success = True
            except:
                print("   [Info] Cookieログイン失敗（期限切れ等）。通常ログインへ移行します。")
                driver.get(target_url)

        if not login_success:
            # ★サーバー遅延対策: ログイン成功を確認し、失敗時は1回やり直す
            login_with_password(driver, target_url)

            # ★サーバー遅延対策: 予約履歴ボタンの待ちを10秒→30秒に延長
            try:
                click_strict(driver, "//main//a[contains(@href,'reserve')] | //main//button[contains(text(),'予約履歴')]", timeout=30)
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
            start_url = driver.current_url
            click_strict(driver, "//span[@class='link-btn']/a[text()='点検']")
            handle_popups(driver, start_url)
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
        # ★タブ一式の描画を待ってから、任意タブ（エンジン等）の有無を判定する
        wait_tab_bar(driver)

        # エンジン（基本点検時は存在しない）→ フル/基本の判定にも使用
        is_full_inspection = open_tab(driver, "div[data-name='engine']", optional=True, may_be_current=True)
        if is_full_inspection:
            fill_active_tab_radios(driver, "日常点検/エンジン")

        # タイヤ（フル・基本共通）
        # 基本点検時はタイヤが最初のタブ（既に表示中の可能性あり）
        open_tab(driver, "div[data-name='tire']", may_be_current=not is_full_inspection)
        fill_active_tab_radios(driver, "日常点検/タイヤ")

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

        # 動作確認（フル・基本共通）
        open_tab(driver, "div[data-name='motion']")
        fill_active_tab_radios(driver, "日常点検/動作確認")

        # 車載品（基本点検時は存在しない）
        if open_tab(driver, "div[data-name='in-car']", optional=True):
            fill_active_tab_radios(driver, "日常点検/車載品")

        # 装備（基本点検時は存在しない）
        if open_tab(driver, "div[data-name='equipment']", optional=True):
            fill_active_tab_radios(driver, "日常点検/装備")

        # 灯火（フル・基本共通）
        # フル点検時: turnSignalを入力（juniorSeatが未入力のため一時保存ボタンが出る）
        # 基本点検時: turnSignalをスキップ（SKIP_NAMES経由で未入力のまま → 一時保存ボタン維持）
        if is_full_inspection:
            SKIP_NAMES.remove("turnSignal")
        open_tab(driver, "div[data-name='light']")
        fill_active_tab_radios(driver, "日常点検/灯火")
        if is_full_inspection:
            SKIP_NAMES.append("turnSignal")

        # 車両周り（基本点検時は存在しない）
        if open_tab(driver, "div[data-name='perimeter']", optional=True):
            fill_active_tab_radios(driver, "日常点検/車両周り")

        # トランク（基本点検時は存在しない）
        if open_tab(driver, "div[data-name='trunk']", optional=True):
            fill_active_tab_radios(driver, "日常点検/トランク")

        # === 一時保存 ===
        print("   一時保存をクリック...")
        start_url = driver.current_url
        click_main_action_button(driver, "save")
        handle_popups(driver, start_url)
        wait_for_return_page(driver)

        # [4] 車内清掃
        print("\n--- [4] 車内清掃 ---")
        click_section_button(driver, "車内清掃")
        fill_active_tab_radios(driver, "車内清掃")

        start_url = driver.current_url
        click_main_action_button(driver, "complete")
        handle_popups(driver, start_url)
        wait_for_return_page(driver)

        # [5] 洗車（基本点検時は存在しない）
        print("\n--- [5] 洗車 ---")
        if click_section_if_exists(driver, "洗車"):
            fill_active_tab_radios(driver, "洗車")
            start_url = driver.current_url
            click_main_action_button(driver, "complete")
            handle_popups(driver, start_url)
            wait_for_return_page(driver)

        # [6] 外装確認
        print("\n--- [6] 外装確認 ---")
        click_section_button(driver, "外装確認")
        fill_active_tab_radios(driver, "外装確認")

        start_url = driver.current_url
        click_main_action_button(driver, "complete")
        handle_popups(driver, start_url)
        wait_for_return_page(driver)

        print("\n=== SUCCESS: 全工程完了 ===")
        if EMPTY_AREAS:
            # ★入力項目が見つからなかったエリアがあれば、完了通知に添えて確認を促す
            send_discord_notification(f"[{plate}] TMAへの入力が完了しました（要確認: 入力項目が見つからなかった箇所 {', '.join(EMPTY_AREAS)}）")
        else:
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
