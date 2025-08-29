# test_update_debug.py
import hmac
import hashlib
import time
import requests
import json
import datetime
from datetime import timezone
from bs4 import BeautifulSoup

# --- 🎈 테스트를 위해 직접 입력해주세요 ---
ACCESS_KEY = "39acc047-446a-4d29-a209-c00be1d886fd"
SECRET_KEY = "5c999c330722e81fba07ff7d7341d49a41c4eb31"
VENDOR_ID = "A00835730"  # 본인 쿠팡 판매자 ID
TEST_PRODUCT_ID = 14846946480  # 업데이트를 테스트할 상품의 sellerProductId
NEW_IMAGE_URL = "http://사장님EMS주소/new_exp_image.jpg" # 새로 바꿀 소비기한 이미지의 전체 URL

DOMAIN = "https://api-gateway.coupang.com"

# --- API 서명 생성 함수 ---
def generate_signature(method, path, secret_key, access_key, query=""):
    now = datetime.datetime.now(timezone.utc)
    timestamp = now.strftime("%y%m%dT%H%M%S") + "Z"
    message = timestamp + method + path + query
    signature = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={timestamp}, signature={signature}"

# --- 1. 특정 상품의 전체 JSON 정보를 가져오는 함수 ---
def get_product_full_json(product_id):
    path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{product_id}"
    try:
        auth = generate_signature("GET", path, SECRET_KEY, ACCESS_KEY)
        response = requests.get(DOMAIN + path, headers={"Authorization": auth})
        response.raise_for_status()
        print("✅ 1. 상품의 현재 정보를 성공적으로 가져왔습니다.")
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"🔥 1. 상품 정보 조회 실패: {e.response.text}")
        return None

# --- 2. '상품 수정(승인필요)' API로 업데이트를 요청하는 함수 (디버깅 추가) ---
def request_product_update(product_id, image_url):
    print("✅ 2. 상품 정보 수정을 시작합니다.")
    
    product_json = get_product_full_json(product_id)
    if not product_json: return

    try:
        is_modified = False
        print("\n--- [디버깅] 상세설명(contents) 분석 시작 ---")
        items = product_json.get('data', {}).get('items', [])
        print(f"발견된 옵션(items) 개수: {len(items)}")

        for i, item in enumerate(items):
            print(f"\n[옵션 #{i+1} 처리중...]")
            contents = item.get('contents', [])
            print(f" - 발견된 contents 블록 개수: {len(contents)}")

            for j, content_block in enumerate(contents):
                print(f"  [contents 블록 #{j+1} 처리중...]")
                content_type = content_block.get('contentsType')
                print(f"   - contentsType: '{content_type}'")

                if content_type == 'HTML':
                    print("   - ✅ 조건 일치: HTML 타입입니다. 상세 분석을 시작합니다.")
                    content_details = content_block.get('contentDetails', [])
                    
                    for k, detail in enumerate(content_details):
                        print(f"     [contentDetail #{k+1} 처리중...]")
                        original_html = detail.get('content', '')
                        if original_html:
                            print("      - HTML 내용을 발견했습니다. 이미지 태그를 검색합니다...")
                            soup = BeautifulSoup(original_html, 'lxml')
                            first_image_tag = soup.find('img')
                            if first_image_tag:
                                print("       - ✅ <img> 태그를 찾았습니다! 이미지 URL을 교체합니다.")
                                first_image_tag['src'] = image_url
                                detail['content'] = str(soup)
                                is_modified = True
                            else:
                                print("       - ⚠️ <img> 태그를 찾지 못했습니다.")
                        else:
                            print("      - ⚠️ HTML 내용이 비어있습니다.")
                else:
                    print("   - ❌ 조건 불일치: HTML 타입이 아니므로 건너뜁니다.")

        print("\n--- [디버깅] 상세설명 분석 종료 ---\n")
        
        if not is_modified:
            print("   - 최종 결과: 변경할 이미지를 찾지 못해 수정을 요청하지 않습니다.")
            return

        # 수정된 내용으로 업데이트 요청
        path_put = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        auth_put = generate_signature("PUT", path_put, SECRET_KEY, ACCESS_KEY)
        headers = {"Authorization": auth_put, "Content-Type": "application/json", "X-VENDOR-ID": VENDOR_ID}
        
        print("✅ 3. 쿠팡에 수정된 정보를 전송합니다...")
        response_put = requests.put(DOMAIN + path_put, headers=headers, data=json.dumps(product_json))
        response_put.raise_for_status()
        print(f"✅ 4. 수정 요청 성공! (HTTP 상태 코드: {response_put.status_code})")

    except Exception as e:
        print(f"🔥 처리 중 오류 발생: {e}")

# --- 스크립트 실행 ---
if __name__ == "__main__":
    print(f"--- 상품 업데이트 테스트 시작 (상품 ID: {TEST_PRODUCT_ID}) ---")
    request_product_update(TEST_PRODUCT_ID, NEW_IMAGE_URL)
    print("--- 테스트 종료 ---")
