import requests, re

html = open('local_test/bill_page.html', encoding='utf-8').read()
urls = set(re.findall(r'src="(/_next/static/chunks/[^"]+)"', html))
print(f"Found {len(urls)} chunks.")

for u in sorted(urls):
    full_url = 'https://sandbox-bill.cashpay.tg' + u
    try:
        txt = requests.get(full_url, timeout=10).text
        for kw in ['redirect_url', 'payment-return', 'return_url']:
            if kw in txt:
                print(f"MATCH: {u} contains '{kw}'")
                # find context around match
                idx = 0
                while True:
                    idx = txt.find(kw, idx)
                    if idx == -1:
                        break
                    start = max(0, idx - 100)
                    end = min(len(txt), idx + 200)
                    print(f"   Context: ...{txt[start:end]}...\n")
                    idx += len(kw)
    except Exception as e:
        print(f"Error {u}: {e}")
