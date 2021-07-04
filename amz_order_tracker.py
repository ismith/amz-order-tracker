#!/usr/bin/env python3

import urllib
from urllib.parse import urlparse
from timer import Timer
import json
from datetime import datetime, timedelta
import dateparser

import selenium
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from dotenv import dotenv_values
from itertools import filterfalse
from tqdm import tqdm
from p_tqdm import p_map


# https://docs.python.org/3/library/itertools.html#recipes
def unique_everseen(iterable, key=None):
    "List unique elements, preserving order. Remember all elements ever seen."
    # unique_everseen('AAAABBBCCDAABBB') --> A B C D
    # unique_everseen('ABBCcAD', str.lower) --> A B C D
    seen = set()
    seen_add = seen.add
    if key is None:
        for element in filterfalse(seen.__contains__, iterable):
            seen_add(element)
            yield element
    else:
        for element in iterable:
            k = key(element)
            if k not in seen:
                seen_add(k)
                yield element


def start_driver():
    driver = webdriver.Chrome(service_args=["--verbose"])
    login(driver)

    return driver


def fork_driver(orig_driver):
    all_cookies = orig_driver.get_cookies()

    new_driver = webdriver.Chrome(service_args=["--verbose"])
    new_driver.get("https://www.amazon.com")
    for cookie in all_cookies:
        new_driver.add_cookie(cookie)

    return new_driver


def login(driver):
    config = dotenv_values(".env")

    login_url = """https://www.amazon.com/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F%3Fref_%3Dnav_custrec_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=usflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&"""
    driver.get(login_url)
    driver.find_element(By.ID, "ap_email").send_keys(config["email"], Keys.RETURN)
    driver.find_element(By.ID, "ap_password").send_keys(config["password"], Keys.RETURN)

    max_delay = 10  # seconds
    WebDriverWait(driver, max_delay).until(EC.title_contains("Amazon.com"))


def orders_page_get_urls(driver):
    # Defaults to past 3 months
    orders_url = "https://www.amazon.com/gp/css/order-history?ref_=nav_orders_first"
    driver.get(orders_url)

    track_package_urls = []
    page_count = 0

    # Get all the "Track package" links from the page, then click "Next→", until
    # you've covered all the pages.
    try:
        while True:
            page_count += 1
            print("Page: {}".format(page_count))
            locator = (By.LINK_TEXT, "Track package")
            max_delay = 1  # seconds
            # Wait until at least 1 "Track package" has shown up
            try:
                WebDriverWait(driver, max_delay).until(
                    EC.visibility_of_element_located(locator)
                )
            except TimeoutException:
                pass

            tp_urls = [
                tp.get_attribute("href")
                for tp in driver.find_elements(By.LINK_TEXT, "Track package")
            ]
            # print("Page {} had {} packages".format(page_count, len(tp_urls)))
            track_package_urls.extend(tp_urls)

            # TODO: can we get the page # from the DOM?
            driver.find_element(By.LINK_TEXT, "Next→").click()
    except selenium.common.exceptions.NoSuchElementException:
        # The 'Next→' button is no longer a link, so we're at the end of the
        # orders.
        pass

    if False:
        print(
            "Processed {} pages, got {} track_package_urls",
            page_count,
            track_package_urls,  # noqa:E501
        )

    return (track_package_urls, page_count)


def get_data_from_track_package_url(cookies, tp_url):
    driver = webdriver.Chrome(service_args=["--verbose"])
    driver.get("https://www.amazon.com")
    for cookie in cookies:
        driver.add_cookie(cookie)

    max_delay = 2
    driver.get(tp_url)

    try:
        WebDriverWait(driver, max_delay).until(
            EC.any_of(
                EC.visibility_of_element_located(
                    (By.CLASS_NAME, "carrierRelatedInfo-trackingId-text")
                ),
                EC.visibility_of_element_located(
                    (By.CLASS_NAME, "milestone-primaryMessage")
                ),
            )
        )
        # This didn't seem to work, try again later - we want to get
        # milestone-... as a fallback
        WebDriverWait(driver, max_delay).until(
            EC.visibility_of_element_located(
                (By.ID, "primaryStatus"),
            )
        )
    except TimeoutException:
        # It's _probably_ fine-and-worth-skipping if we get a timeout; not all
        # orders have tracking info (Fresh, maybe older orders) and we want to
        # skip those.
        pass

    try:
        trackingId = driver.find_element(
            By.CLASS_NAME, "carrierRelatedInfo-trackingId-text"
        ).text.replace("Tracking ID: ", "", 1)
    except:  # noqa:#722
        trackingId = ""

    try:
        milestone = driver.find_element(By.CLASS_NAME, "milestone-primaryMessage").text
    except:  # noqa:#722
        milestone = ""

    status = driver.find_element(By.ID, "primaryStatus").text

    _orderContainer = driver.find_element(By.ID, "ordersInPackage-container")
    _orders = _orderContainer.find_elements(By.CLASS_NAME, "a-link-normal")
    _orderLinks = [orderLink.get_attribute("href") for orderLink in _orders]
    orderIds = [
        urllib.parse.parse_qs(urlparse(orderLink).query)["orderID"][0]
        for orderLink in _orderLinks
    ]

    datum = {
        "status": status,
        "milestone": milestone,
        "trackingId": trackingId,
        "orderIds": list(set(orderIds)),
        "url": tp_url,
    }

    # print("DATUM: {}".format(datum))

    driver.quit()  # TODO with?

    return datum


# Betcha we could get the cookies from the driver and spin up moar instances to
# run in parallel
def get_data_from_urls(driver, urls):
    # Does p_map take leave/unit?
    all_cookies = driver.get_cookies()
    data = p_map(lambda url: get_data_from_track_package_url(all_cookies, url), urls)
    #    for url in tqdm(urls, leave=True, unit="pkg url"):
    #        datum = get_data_from_track_package_url(driver, url)
    #
    #        data.append(datum)

    # Throw out anything more than a week old. This is not the performant way
    # to do this (we could probably filter this at an earlier step), but it's
    # the easiest to write right now.

    data2 = []

    f = open("orders-received.json")
    j = json.load(f)
    skipOrders = j["skip"]["orders"]
    skipTPAs = j["skip"]["tpas"]
    for d in unique_everseen(data, lambda d: d["trackingId"] or d["orderIds"][0]):
        # If it's in the skip list, skip it.
        if [v for v in d["orderIds"] if v in skipOrders]:
            continue

        if d["trackingId"] in skipTPAs:
            continue

        try:
            date = dateparser.parse(
                d["status"].replace("Delivered ", "", 1).replace("Arriving ", "", 1)
            )
            target = datetime.now() - timedelta(days=7)

            if d["status"] == "Your package may be lost" or date > target:
                data2.append(d)
        except TypeError as e:
            print("Error", e)

    print("len(data, data2, urls): {}", len(data), len(data2), len(urls))
    return data2


if __name__ == "__main__":
    try:
        with Timer(text="Start driver: {:.3f}"):
            driver = start_driver()
        with Timer(text="orders_page_get_urls: {:.3f}"):
            (urls, _) = orders_page_get_urls(driver)
        with Timer(text="get_data_from_urls: {:.3f}"):
            data = get_data_from_urls(driver, urls)

        print(json.dumps(data, indent=2))
    finally:
        # Should start_driver return a context?
        driver.quit()
