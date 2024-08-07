from celery import shared_task
from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity

import openai

import os
import base64
from datetime import datetime

from ..models.transactions import FundTransactionRecord


# 将图片编码为base64发送
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def parse_fund_purchase_info(input_string):
    # 分割输入字符串并去除多余的空格
    lines = input_string.strip().split('\n')
    # 初始化字典
    result = {}
    # 定义字典的键
    keys = ["amount", "time", "nav", "shares", "fee", "fund_name", "type"]

    for line in lines:
        # 分割每一行内容，获取键和值
        key, value = line.split('#')
        # 将键转换为对应的字典键
        dict_key = keys[int(key) - 1]
        # 将数值字符串转换为浮点数，时间和基金名称保持字符串格式
        if dict_key == "time" or dict_key == "fund_name":
            result[dict_key] = value
        elif dict_key == "type":
            if value == "买入":
                result[dict_key] = "buy"
            elif value == "卖出":
                result[dict_key] = "sell"
            elif value == "定投":
                result[dict_key] = "auto_invest"
            elif value == "分红":
                result[dict_key] = "dividend"
            else:
                result[dict_key] = "none"
        else:
            result[dict_key] = float(value)
    return result


def match_fund_name_with_name_and_code(fund_name):
    # 从给定的fund_name中匹配名称最像的基金，返回这个最像的基金名称和对应代码
    from domestic.models.fund_models import FundInfo
    matched_fund = FundInfo.objects.annotate(
        similarity=TrigramSimilarity('name', fund_name)
    ).filter(
        similarity__gt=0.1
    ).order_by('-similarity')

    # 如果没有搜索到结果，就返回两个None
    if not matched_fund:
        return None, None

    # 输出搜索结果
    # for fund in matched_fund:
    #     print(f"Found fund: {fund.name}, similarity: {fund.similarity}")

    # 取前两个搜索结果
    first_match = matched_fund.first()
    second_match = matched_fund[1]

    print(f"first match: {first_match.name}, second_match: {second_match.name}")

    # 提取出first_match.name从最后开始往前数第一个英文字符
    first_match_last_char = ''
    for i in range(len(first_match.name) - 1, -1, -1):
        if 'A' <= first_match.name[i] <= 'Z':
            first_match_last_char = first_match.name[i]
            break
    # 提取出second_match.name从最后开始往前数第一个英文字符
    second_match_last_char = ''
    for i in range(len(second_match.name) - 1, -1, -1):
        if 'A' <= second_match.name[i] <= 'Z':
            second_match_last_char = second_match.name[i]
            break

    # 提取出fund_name从最后开始往前数第一个英文字符
    fund_name_last_char = ''
    for i in range(len(fund_name) - 1, -1, -1):
        if 'A' <= fund_name[i] <= 'Z':
            fund_name_last_char = fund_name[i]
            break

    print(f"Last alphabet for first_natch, second_match and fund_name: {first_match_last_char}, {second_match_last_char}, {fund_name_last_char}")

    # 若第一个搜索结果的最后一个英文字符（一般指示基金份额）和fund_name的最后一个英文字符相符，则直接返回这个基金的名称和代码
    if first_match_last_char == fund_name_last_char:
        return first_match.name, first_match.ts_code
    # 第二个同理
    elif second_match_last_char == fund_name_last_char:
        return second_match.name, second_match.ts_code

    # 默认返回第一个
    return first_match.name, first_match.ts_code





@shared_task(bind=True)
def create_records_from_local_images(self, sub_dir=None):
    # 从resources/alpharecord/prompts/get_fund_transaction_info.txt中加载prompt
    with open('resources/alpharecord/prompts/get_fund_transaction_info.txt', 'r') as prompt_file:
        prompt = prompt_file.read()

    primary_vlm = settings.PRIMARY_VLM

    if primary_vlm == 'qwen-vl-max' or primary_vlm == 'qwen-vl-plus':
        vlm_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        vlm_api_key = settings.DASHSCOPE_API_KEY
    else:
        vlm_base_url = "https://openrouter.ai/api/v1"
        vlm_api_key = settings.OPENROUTER_API_KEY

    model_name = primary_vlm

    client = openai.OpenAI(
        base_url=vlm_base_url,
        api_key=vlm_api_key,
    )

    transaction_results = []

    # 默认需要处理的图片都在resources/temp/alpharecord/upload下
    # 遍历这个目录下的图片

    if sub_dir is not None:
        images_dir = os.path.join('resources/temp/alpharecord/upload', sub_dir)
    else:
        images_dir = 'resources/temp/alpharecord/upload'

    counter = 0

    for root, dirs, files in os.walk(images_dir):
        for file in files:
            counter += 1
            task_result = {
                'progress': f"正在处理第{counter}张",
                'code': 0
            }
            self.update_state(state='PROGRESS', meta=task_result)
            image_path = os.path.join(root, file)
            image_base64 = encode_image(image_path)
            print(f"正在处理图片：{image_path}")
            response = client.chat.completions.create(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": prompt,
                    }, {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        },
                    }, ],
                }],
                temperature=0
            )
            print(f"测试响应：{response.choices[0].message.content}")
            transaction_dict = parse_fund_purchase_info(response.choices[0].message.content)
            # print(transaction_dict)
            fund_database_name, ts_code = match_fund_name_with_name_and_code(transaction_dict['fund_name'])
            # transaction_dict['time'] = datetime.strptime(transaction_dict['time'], '%Y/%m/%d %H:%M:%S')
            print(f"匹配到的基金名称：{fund_database_name}，基金代码：{ts_code}")
            if ts_code:
                transaction_dict['fund_database_name'] = fund_database_name
                transaction_dict['ts_code'] = ts_code
                # 基金购买平台需要用户自己补充
                transaction_dict['platform'] = ""
                transaction_dict['index'] = counter
                transaction_results.append(transaction_dict)
            else:
                task_result = {
                    'progress': f"No fund found for {transaction_dict['fund_name']}",
                    'code': -1
                }
                self.update_state(state='FAILURE', meta=task_result)
                return task_result



    task_result = {
        'progress': 'All images processed',
        'transaction_results': transaction_results,
        'code': 0
    }
    self.update_state(state='SUCCESS', meta=task_result)
    
    return task_result


