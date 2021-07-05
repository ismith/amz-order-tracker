# amz-order-tracker

# What is it?
When run (`. ./venv/bin/activate ; ./amz_order_tracker.py`), gets the last 90 days of your order history from Amazon, and prints
out a list of packages (or packages-not-yet-sent):
```json
[
  {
    "status": "Arriving Wednesday",
    "milestone": "Ordered Sunday, July 4",
    "trackingId": "", // empty because it hasn't yet shipped
    "orderIds": [
      ... // a package 
    ],
    "url": "[url to the order's tracking page"
  },
  ...
]
```

You must provide a `.env` file with your login info:
```
email=...
password=...
```

Sometimes Amazon will prompt you for 2FA, presumably because Selenium logs in
fast enough to be suspicious? Fortunately, all you do is have to tap the link or
button in your phone notifications.

## Options
If you create an `orders-received.json` file, you can skip packages or orders
you've already received:

```json
{
  "skip": {
    "orders": [ "111-1234567-1234567" ],
    "tpas": [ "TBA..." ]
  }
}
```

## Prereqs
You'll need a Selenium ChromeDriver:
```bash
# OS X
brew cask install chromedriver

# Ubuntu
sudo apt install chromium-chromedriver
```

You'll also need have python3 and install its dependencies:
```
# pip or  pip3 depending on your env. Or use venv.
pip install -r requirements.txt
```
