import requests

url = "https://www.paynow.co.zw/Payment/ConfirmPayment/58585178"
response = requests.get(
    url,
    headers={"User-Agent": "VerityAI-Paynow-Live-Check/1.0"},
    timeout=20,
    allow_redirects=False,
)
body = " ".join(response.text.lower().split())
print("status", response.status_code)
print(
    "test_marker",
    any(
        marker in body
        for marker in (
            "testing: faked success",
            "currently in testing",
            "cannot accept payments at this time",
        )
    ),
)
print("currency_usd", "usd 12.00" in body)
print("currency_zwg", "zwg12.00" in body or "zwg 12.00" in body)
