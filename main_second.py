import os
import hmac
import hashlib
import time
import requests
from bs4 import BeautifulSoup
import json
import datetime
from datetime import timezone

# --- 설정값 ---
ACCESS_KEY = os.environ.get('COUPANG_ACCESS_KEY')
SECRET_KEY = os.environ.get('COUPANG_SECRET_KEY')
VENDOR_ID = "A00835730"  # 본인 쿠팡 판매자 ID (WING 로그인 ID)
IMAGE_FIXED_URL = "https://gi.esmplus.com/na100shop/mall/mall_top.jpg"

DOMAIN = "https://api-gateway.coupang.com"

# --- API 서명 생성 함수 ---
def generate_signature(method, path, secret_key, access_key, query=""):
    now = datetime.datetime.now(timezone.utc)
    timestamp = now.strftime("%y%m%dT%H%M%S") + "Z"
    message = timestamp + method + path + query
    signature = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={timestamp}, signature={signature}"

# --- 1. 판매 중인 모든 상품 ID 가져오는 함수 (오류 수정) ---
def get_all_product_ids():
    print("1. '상품 목록 페이징 조회' API로 조회를 시작합니다...")
    product_ids = []
    # next_token을 문자열로 다루고, 첫 페이지는 "1"로 시작합니다.
    next_token = "1"
    page_count = 1

    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"

    while next_token:
        # 💡 [핵심 수정사항] 쿼리 생성 로직을 더 안전하게 변경했습니다.
        query_params = {
            "vendorId": VENDOR_ID,
            "maxPerPage": 100,
            "nextToken": next_token
        }
        # 쿼리스트링 생성 (예: vendorId=A...&maxPerPage=100&nextToken=1)
        query_for_signature = "&".join([f"{k}={v}" for k, v in query_params.items()])
        query_for_request = f"?{query_for_signature}"

        try:
            auth = generate_signature("GET", path, SECRET_KEY, ACCESS_KEY, query_for_signature)
            headers = {"Authorization": auth}

            response = requests.get(DOMAIN + path + query_for_request, headers=headers)
            response.raise_for_status()
            data = response.json()

            products_on_page = data.get('data', [])
            if not products_on_page:
                break

            for item in products_on_page:
                product_ids.append(item['sellerProductId'])

            print(f"   - {page_count} 페이지에서 상품 {len(products_on_page)}개 발견. (총 {len(product_ids)}개)")

            # 다음 페이지를 위해 응답에 포함된 nextToken 값을 사용합니다.
            next_token = data.get('nextToken')
            if not next_token: # nextToken이 비어있거나 null이면 마지막 페이지이므로 종료
                break

            page_count += 1
            time.sleep(0.5)

        except requests.exceptions.HTTPError as e:
            print(f"상품 목록 조회 실패: {e.response.text}")
            return []

    print(f"총 {len(product_ids)}개의 상품 ID를 성공적으로 가져왔습니다.")
    return product_ids

# --- 2. 특정 상품의 전체 JSON 정보를 가져오는 함수 ---
def get_product_full_json(product_id):
    path = f"/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{product_id}"
    try:
        auth = generate_signature("GET", path, SECRET_KEY, ACCESS_KEY)
        response = requests.get(DOMAIN + path, headers={"Authorization": auth})
        response.raise_for_status()
        return response.json().get('data', {})
    except requests.exceptions.HTTPError as e:
        print(f"   상품 ID {product_id} 정보 조회 실패: {e.response.text}")
        return None

# --- 3. 상품 수정 요청 함수 ---
def request_product_update(product_id, image_url):
    print(f"\n--- 상품 ID {product_id} 업데이트 작업 시작 ---")
    product_json = get_product_full_json(product_id)
    if not product_json: return
    try:
        is_modified = False
        for item in product_json.get('items', []):
            for content_block in item.get('contents', []):
                if content_block.get('contentsType') == 'HTML':
                    for detail in content_block.get('contentDetails', []):
                        soup = BeautifulSoup(detail.get('content', ''), 'lxml')
                        all_images = soup.find_all('img')
                        if len(all_images) >= 2:
                            second_image = all_images[1]
                            second_image['src'] = image_url
                            detail['content'] = str(soup)
                            is_modified = True
                        else:
                            print(f"   - 상품 ID {product_id}에 이미지가 2개 미만이라 수정하지 않습니다.")
        if not is_modified:
            print("   - 수정할 내용이 없어 건너뜁니다.")
            return

        keys_to_remove = ["statusName", "productId", "mdId", "mdName", "contributorType", "status", "roleCode", "trackingId"]
        for key in keys_to_remove:
            if key in product_json: del product_json[key]
        for item in product_json.get('items', []):
            item_keys_to_remove = ["vendorItemId", "itemId", "isAutoGenerated"]
            for key in item_keys_to_remove:
                if key in item: del item[key]

        product_json['requested'] = True

        path_put = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
        auth_put = generate_signature("PUT", path_put, SECRET_KEY, ACCESS_KEY)
        headers = {"Authorization": auth_put, "Content-Type": "application/json", "X-VENDOR-ID": VENDOR_ID}

        response_put = requests.put(DOMAIN + path_put, headers=headers, data=json.dumps(product_json))
        response_put.raise_for_status()
        print(f"   수정 및 승인 요청 성공!")
    except Exception as e:
        print(f"   처리 중 오류 발생: {e}")

# --- 메인 실행 함수 ---
def main():
    print("쿠팡 전체 상품 이미지 업데이트 자동화를 시작합니다.")
    product_ids = get_all_product_ids()
    if not product_ids:
        print("작업할 상품이 없습니다. 종료합니다.")
        return

    cache_buster = f"?v={int(time.time())}"
    final_image_url = IMAGE_FIXED_URL + cache_buster
    print(f"\n적용할 이미지 URL: {final_image_url}\n")

    for pid in product_ids:
        request_product_update(pid, final_image_url)
        time.sleep(1)

    print("\n모든 상품에 대한 작업이 완료되었습니다. 쿠팡 WING에서 최종 승인 상태를 확인해주세요.")

if __name__ == "__main__":
    main()