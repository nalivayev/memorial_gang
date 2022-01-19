from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementClickInterceptedException
from selenium.webdriver.support.expected_conditions import element_to_be_clickable
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver import Firefox
from argparse import ArgumentParser
from threading import Thread
from typing import Any

import datetime
import logging
import shutil
import os


class MarauderException(Exception):
    pass


class MarauderParser(ArgumentParser):

    __required_group: Any

    def __init__(self):
        ArgumentParser.__init__(self)
        self.__required_group = self.add_argument_group("required arguments")
        self.__required_group.add_argument("-i", "--id", type=int, help="file identifier, e. g. 7766809", required=True, default=None)
        self.add_argument("-s", "--skip", type=bool, help="skip existing files")
        self.add_argument("-c", "--count", type=int, help="count of files")
        self.add_argument("-gc", "--groupcount", type=int, help="count of files in group")
        self.add_argument("-ga", "--groupaligment", type=bool, help="align directories by group")
        self.add_argument("-fc", "--flowcount", type=int, help="count of download flow")
        self.add_argument("-st", "--step", type=int, help="step between identifiers")

    def parse_args(self, args=None, namespace=None):
        v_result = ArgumentParser.parse_args(self, args, namespace)
        if v_result.id:
            if v_result.id < 1:
                self.error("Incorrect file identifier")
        else:
            self.error("Incorrect file identifier")
        if v_result.count and v_result.count < 1:
            self.error("Incorrect count value. The parameter must be a greater than 0")
        if v_result.groupcount and v_result.groupcount < 1:
            self.error("Incorrect group count value. The parameter must be a greater than 0")
        if v_result.step and v_result.step < 1:
            self.error("Incorrect step value. The parameter must be a greater than 0")
        if v_result.flowcount and v_result.flowcount < 1:
            self.error("Incorrect flow count value. The parameter must be a greater than 0")
        return v_result


class MarauderLogger:

    __logger: logging.Logger

    def __init__(self):
        self.__logger = logging.getLogger("marauder")
        self.__logger.setLevel(logging.INFO)
        v_formatter = logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
        v_handler = logging.FileHandler(f"{os.path.splitext(__file__)[0]}.log", mode="w")
        v_handler.setFormatter(v_formatter)
        self.__logger.addHandler(v_handler)
        v_handler = logging.StreamHandler()
        v_handler.setFormatter(v_formatter)
        self.__logger.addHandler(v_handler)

    def info(self, p_message: str) -> None:
        self.__logger.info(p_message)


class Marauder:

    __URL = "https://obd-memorial.ru/html/search.htm?f=галочкин&n=иван&s=михайлович"
    __EXTENSIONS = ["jpg", "JPG", "jpeg", "JPEG", "png", "PNG", "bmp", "BMP"]
    __PROXY_ELEMENT_ID_DOWNLOAD_XPATH = "//span[@id_download='{id}']"
    __PROXY_ELEMENT_CLASS_XPATH = "//span[@class='searchResultDownload']"
    __LOAD_TIMEOUT = 30
    __RESTART_COUNT = 10

    __driver: Firefox = None
    __logger: MarauderLogger = None
    __element: WebElement = None
    __id: int = 0
    __skip: bool = False
    __count: int = 0
    __group_count: int = 0
    __group_alignment: bool = False
    __restart_count: int = 0
    __step: int = 1
    __flow_id: str
    __list: []

    @staticmethod
    def __make_root_name():
        return os.path.dirname(os.path.realpath(__file__))

    def __add_log_message(self, p_message):
        if self.__logger is not None:
            self.__logger.info(p_message)

    def __make_path_name(self, p_id):
        if self.__id:
            if self.__group_count and self.__group_count > 0:
                if self.__group_alignment:
                    v_number = (p_id // self.__group_count) * self.__group_count
                else:
                    v_number = self.__id + ((p_id - self.__id) // self.__group_count) * self.__group_count
                v_result = f"{str(v_number).rjust(9, '0')}.{str(v_number + self.__group_count - 1).rjust(9, '0')}"
            else:
                v_result = f"{str(self.__id).rjust(9, '0')}"
        else:
            v_result = ""
        return os.path.join(self.__make_root_name(), v_result)

    def __make_temporary_path_name(self):
        return os.path.join(self.__make_root_name(), "temporary")

    def __check_for_existence(self, p_id):
        v_result = False
        if p_id > 0:
            v_path_name = self.__make_path_name(p_id)
            for v_extension in self.__EXTENSIONS:
                v_file_name = os.path.join(v_path_name, f"{p_id}.{v_extension}")
                if os.path.exists(v_file_name):
                    v_result = True
                    break
        return v_result

    def __start_new_session(self):
        self.__add_log_message(f"{self.__flow_id} Start new browser session")
        v_path = self.__make_temporary_path_name()
        if not os.path.exists(v_path):
            os.makedirs(v_path)
        v_profile = FirefoxProfile()
        v_profile.set_preference("browser.download.panel.shown", False)
        v_profile.set_preference("browser.helperApps.neverAsk.openFile", "image/jpeg")
        v_profile.set_preference("browser.helperApps.neverAsk.saveToDisk", "image/jpeg")
        v_profile.set_preference("browser.download.folderList", 2)
        v_profile.set_preference("browser.download.dir", v_path)
        v_options = Options()
        v_options.add_argument("--headless")
        self.__driver = Firefox(firefox_options=v_options, firefox_profile=v_profile)
        self.__driver.get(self.__URL)
        WebDriverWait(self.__driver, self.__LOAD_TIMEOUT).until(element_to_be_clickable((By.XPATH, self.__PROXY_ELEMENT_CLASS_XPATH)))
        self.__element = self.__driver.find_element_by_xpath(self.__PROXY_ELEMENT_CLASS_XPATH)
        if not self.__element:
            raise NoSuchElementException

    def __remove_temporary_path(self):
        v_path = self.__make_temporary_path_name()
        if os.path.exists(v_path):
            try:
                shutil.rmtree(v_path, ignore_errors=True)
            except Exception:
                self.__add_log_message(f"{self.__flow_id} Error while remove temporary folder")

    def __restart(self):
        self.__add_log_message(f"{self.__flow_id} Restart marauding")
        if self.__driver:
            self.__driver.quit()
        # self.__remove_temporary_path()
        if self.__restart_count < self.__RESTART_COUNT:
            self.__restart_count += 1
            try:
                self.__start_new_session()
            except Exception:
                self.__add_log_message(f"{self.__flow_id} Error while start browser session")
                raise MarauderException
        else:
            self.__add_log_message(f"{self.__flow_id} Error while restart - restart count exceed")
            raise MarauderException

    def __check_list(self):
        for v_i in range(len(self.__list)):
            v_item = self.__list[0]
            if (datetime.datetime.now() - v_item["moment"]).total_seconds() > 5:
                v_loading = False
                for v_extension in self.__EXTENSIONS:
                    v_from_name = os.path.join(self.__make_temporary_path_name(), f"{v_item['id']}.{v_extension}")
                    if os.path.exists(v_from_name):
                        v_to_path_name = self.__make_path_name(v_item['id'])
                        if not os.path.exists(v_to_path_name):
                            os.makedirs(v_to_path_name)
                        try:
                            shutil.move(v_from_name, os.path.join(v_to_path_name, f"{v_item['id']}.{v_extension}"))
                        except Exception:
                            self.__add_log_message(f"{self.__flow_id} {v_item['id']} Error copying file")
                        else:
                            v_loading = True
                            break
                if v_loading:
                    self.__add_log_message(f"{self.__flow_id} {v_item['id']} Loading complete")
                else:
                    self.__add_log_message(f"{self.__flow_id} {v_item['id']} Not found")
                self.__list.pop(0)

    def do(self, p_logger: MarauderLogger, p_id: int = 1, p_skip: bool = False, p_count: int = None, p_group_count: int = None, p_step: int = None, p_flow_id: str = None, p_group_alignment: bool = False):
        self.__logger = p_logger
        self.__id = p_id
        self.__skip = p_skip
        self.__group_alignment = p_group_alignment
        if p_flow_id:
            self.__flow_id = p_flow_id
        else:
            self.__flow_id = "A"
        if p_id and p_id > 0:
            self.__id = p_id
        else:
            self.__add_log_message(f"{self.__flow_id} Incorrect id value, execution aborted")
            raise MarauderException
        if p_count:
            if p_count >= 0:
                self.__count = p_count
            else:
                self.__add_log_message(f"{self.__flow_id} Incorrect count value, execution aborted")
                raise MarauderException
        if p_group_count:
            if p_group_count > 0:
                self.__group_count = p_group_count
            else:
                self.__add_log_message(f"{self.__flow_id} Incorrect group count value, execution aborted")
                raise MarauderException
        if p_step:
            if p_step > 0:
                self.__step = p_step
            else:
                self.__add_log_message(f"{self.__flow_id} Incorrect step value, execution aborted")
                raise MarauderException
        else:
            self.__step = 1
        try:
            self.__start_new_session()
        except Exception:
            self.__add_log_message(f"{self.__flow_id} Error while start browser session")
            raise
        else:
            v_id = self.__id
            self.__list = []
            while True:
                if self.__count and v_id >= self.__id + self.__count:
                    break
                if self.__skip and self.__check_for_existence(v_id):
                    self.__add_log_message(f"{self.__flow_id} {v_id} File already exists - skip loading")
                else:
                    v_restart = False
                    try:
                        self.__driver.execute_script("arguments[0].setAttribute('id_download', arguments[1]);", self.__element, v_id)
                        WebDriverWait(self.__driver, self.__LOAD_TIMEOUT).until(element_to_be_clickable((By.XPATH, self.__PROXY_ELEMENT_ID_DOWNLOAD_XPATH.format(id=v_id))))
                    except (TimeoutException, NoSuchElementException):
                        self.__add_log_message(f"{self.__flow_id} {v_id} Error while proxy element search")
                        v_restart = True
                    else:
                        try:
                            self.__element.click()
                        except ElementClickInterceptedException:
                            self.__add_log_message(f"{self.__flow_id} {v_id} Error while proxy element clicking")
                            v_restart = True
                        else:
                            self.__list.append({"id": v_id, "moment": datetime.datetime.now()})
                    if v_restart:
                        try:
                            self.__restart()
                            continue
                        except Exception:
                            break
                self.__check_list()
                self.__restart_count = 0
                v_id += self.__step
            if self.__driver:
                self.__driver.quit()
                self.__add_log_message(f"{self.__flow_id} Close browser session")
            while len(self.__list) > 0:
                self.__check_list()
            self.__remove_temporary_path()


class MultiMarauder:

    @staticmethod
    def do(p_logger: MarauderLogger, p_id: int, p_skip: bool, p_count: int, p_group_count: int, p_flow_count: int):

        def do_in_thread(p_thread_logger, p_thread_id, p_thread_skip, p_thread_count, p_thread_group_count, p_thread_flow_count, p_thread_flow_id):
            v_marauder = Marauder()
            v_marauder.do(p_thread_logger, p_thread_id, p_thread_skip, p_thread_count, p_thread_group_count, p_thread_flow_count, p_thread_flow_id, True)

        for v_i in range(p_flow_count):
            v_thread = Thread(target=do_in_thread, args=(p_logger, p_id + v_i, p_skip, p_count, p_group_count, p_flow_count, chr(ord("A") + v_i)))
            v_thread.start()
