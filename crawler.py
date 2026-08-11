import time
import pandas as pd
from datetime import datetime
import pytz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# =================================================================
# 1. CONFIGURAÇÃO DE PARÂMETROS E FILTRO DE DATA
# =================================================================

# URL base do fórum/site alvo (substitua pela URL real do seu projeto)
BASE_URL = "https://exemplo-forum.com/categoria/topicos"

# Intervalo de datas para filtro (formato: 'AAAA-MM-DD')
START_DATE_STR = 'AAAA-MM-DD'
END_DATE_STR = 'AAAA-MM-DD'

DATE_FORMAT_STRING = '%B %d, %Y at %I:%M %p %Z'

# Timezone de referência usada para normalizar as datas do site
try:
    target_tz = pytz.timezone('US/Pacific')
    START_DATE = datetime.strptime(START_DATE_STR, '%Y-%m-%d').replace(hour=0, minute=0, second=0).astimezone(target_tz)
    END_DATE = datetime.strptime(END_DATE_STR, '%Y-%m-%d').replace(hour=23, minute=59, second=59).astimezone(target_tz)
except pytz.UnknownTimeZoneError:
    print("Erro: Timezone desconhecida ou incompatível.")
    exit()
except ValueError:
    print("Erro: Formato de data inválido. Use 'AAAA-MM-DD'.")
    exit()

data_records = []

# =================================================================
# 2. CONFIGURAÇÃO DO SELENIUM E FUNÇÕES AUXILIARES
# =================================================================

CHROME_DRIVER_PATH = None

def initialize_driver():
    """Inicializa o WebDriver do Chrome."""
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (compatible; ExemploBot/1.0)')

    if CHROME_DRIVER_PATH:
        service = Service(CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.implicitly_wait(10)
    return driver

def handle_cookie_popup(driver):
    """Aguarda o pop-up de cookies e tenta recusar/fechar."""
    REJECT_ALL_SELECTOR = '#cookie-reject-all'
    COOKIE_TIMEOUT = 10

    try:
        reject_btn = WebDriverWait(driver, COOKIE_TIMEOUT).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, REJECT_ALL_SELECTOR))
        )
        print("Pop-up de cookies encontrado.")
        reject_btn.click()
        print("Cookies rejeitados com sucesso.")
        time.sleep(2)
    except TimeoutException:
        print("Aviso: Pop-up de cookies não encontrado. Continuando...")
    except NoSuchElementException:
        print("Aviso: Botão de rejeitar cookies não encontrado. Continuando...")
    except Exception as e:
        print(f"Aviso: Erro inesperado ao tratar cookies: {e}. Continuando...")

def parse_date(date_str):
    """Converte a string de data do post para um objeto datetime com timezone."""
    try:
        dt_naive = datetime.strptime(
            date_str.replace(' PST', '').replace(' PDT', '').strip(),
            '%B %d, %Y at %I:%M %p'
        )
        return pytz.timezone('US/Pacific').localize(dt_naive)
    except Exception as e:
        print(f"Erro ao analisar a data: '{date_str}'. Erro: {e}")
        return None

def extract_post_content(driver, url, summary):
    """Navega para um post individual, extrai data e conteúdo, e verifica o intervalo."""

    print(f"   -> Visitando post: {summary[:50]}...")
    driver.get(url)

    try:
        # Seletores genéricos - ajuste conforme a estrutura do site alvo
        date_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span.post-date'))
        )
        date_str_full = date_element.get_attribute("data-tooltip")

        content_element = driver.find_element(By.CSS_SELECTOR, 'div.post-content')
        content = content_element.text

        post_date = parse_date(date_str_full)

        if post_date is None:
            return False, {'Link': url, 'Summary': summary, 'Date': date_str_full, 'Content': "Não foi possível extrair data/conteúdo."}

        if START_DATE <= post_date <= END_DATE:
            record = {
                'Link': url,
                'Date': post_date.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'Summary': summary,
                'Content': content,
                'Category': '',
                'Keyword': ''
            }
            data_records.append(record)
            return True, record

        elif post_date < START_DATE:
            print(f"\nPost mais antigo encontrado: {post_date.strftime('%Y-%m-%d')}. Intervalo atingido. Finalizando.")
            return False, None

        else:
            print(f"   -> Post ignorado (Data: {post_date.strftime('%Y-%m-%d')}) - fora do limite superior.")
            return True, None

    except TimeoutException:
        print(f"   -> Erro: Timeout ao buscar elementos no post {url}. Pulando.")
        return True, {'Link': url, 'Summary': summary, 'Date': 'Timeout', 'Content': 'Timeout ao carregar post.'}
    except NoSuchElementException:
        print(f"   -> Erro: Elemento não encontrado no post {url}. Pulando.")
        return True, {'Link': url, 'Summary': summary, 'Date': 'Elemento não encontrado', 'Content': 'Erro de seletor.'}
    except Exception as e:
        print(f"   -> Erro inesperado ao processar o post {url}: {e}. Pulando.")
        return True, {'Link': url, 'Summary': summary, 'Date': 'Erro inesperado', 'Content': str(e)}

def scrape_forum():
    """Função principal que navega pelas páginas do site alvo."""
    driver = initialize_driver()
    current_list_url = BASE_URL

    current_page = 1
    total_posts_processed = 0

    try:
        driver.get(current_list_url)
        handle_cookie_popup(driver)

        while True:
            driver.get(current_list_url)

            print(f"\n========================================================")
            print(f"Página atual: {current_page}")
            print(f"========================================================")

            # Seletores genéricos - ajuste conforme a estrutura do site alvo
            LIST_SELECTOR = 'ul.post-list'
            LIST_ITEM_SELECTOR = 'li.post-list__item'
            TITLE_LINK_SELECTOR = 'h3 a'

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, LIST_SELECTOR))
                )
            except TimeoutException:
                print("Erro: Timeout ao carregar lista de posts. Fim da coleta.")
                break

            post_elements = driver.find_elements(By.CSS_SELECTOR, LIST_ITEM_SELECTOR)

            if not post_elements:
                print("Nenhum post encontrado na página. Fim da navegação ou erro de seletor.")
                break

            # Extrai URLs e títulos ANTES de navegar, evitando StaleElementReferenceException
            links_to_visit = []
            for post in post_elements:
                try:
                    link_element = post.find_element(By.CSS_SELECTOR, TITLE_LINK_SELECTOR)
                    post_url = link_element.get_attribute('href')
                    post_summary = link_element.text
                    links_to_visit.append((post_url, post_summary))
                except NoSuchElementException:
                    print("Aviso: Link/título do post não encontrado. Ignorando item.")
                    continue

            should_continue_page = True

            for url, summary in links_to_visit:
                can_continue, result = extract_post_content(driver, url, summary)
                total_posts_processed += 1

                if not can_continue and result is None:
                    should_continue_page = False
                    break

                driver.back()
                time.sleep(1)

            if not should_continue_page:
                break

            # Navega para a próxima página
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, 'a[rel="next"]')

                if 'disabled' in next_button.get_attribute('class') or not next_button.is_displayed():
                    print("Botão 'Próximo' desabilitado ou não visível. Fim das páginas.")
                    break

                next_url = next_button.get_attribute('href')
                next_button.click()
                current_list_url = next_url
                current_page += 1

            except NoSuchElementException:
                print("Paginação não encontrada. Assumindo fim do site.")
                break
            except Exception as e:
                print(f"Erro ao navegar para próxima página: {e}")
                break

    finally:
        driver.quit()
        print(f"\n========================================================")
        print(f"Coleta finalizada. Posts processados: {total_posts_processed}.")
        print(f"Posts coletados dentro do intervalo: {len(data_records)}.")
        print(f"========================================================")

# =================================================================
# 3. EXPORTAÇÃO DE DADOS
# =================================================================

if __name__ == "__main__":
    scrape_forum()

    if data_records:
        df = pd.DataFrame(data_records)
        filename = 'posts_coletados.csv'
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"\nDados exportados com sucesso para: {filename}")
    else:
        print("\nNenhuma postagem foi coletada dentro do intervalo de datas especificado.")
