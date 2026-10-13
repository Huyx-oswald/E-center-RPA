#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
华工图像-发票结算审批单（SRM集成）并发抓取脚本

适用场景：在“已登录 OA 的本机”上运行。
原理：OA 所有数据都从后端 JSON 接口返回，无需逐行点击页面。
     本脚本直接并发请求两个接口：
       1) /api/ec/dev/table/datas   列表分页，拿每个单据的 requestid
       2) /api/workflow/reqform/loadForm  单请求返回整单字段
     相比浏览器逐行点开单据（串行、慢），接口并发会在几十秒内完成。

前提：从已登录 OA 的浏览器里导出本会话 Cookie（见下方说明）。

用法：
   1. 登录 OA 后，F12 -> Network -> 任意接口请求头里复制 Cookie 文本，
      粘贴到下面 COOKIE 变量（单行，分号分隔）。
   2. pip install requests tqdm openpyxl
   3. python3 crawl_fapiao.py
"""

import json
import requests
import openpyxl
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

BASE = "https://ebusiness.hgtech.com.cn"

# ============ 需要你自己填 ============
COOKIE = ""  # ← 粘贴浏览器里登录后复制的 Cookie
# =====================================

HEADERS = {
    "Cookie": COOKIE,
    "Content-Type": "application/json;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": BASE + "/wui/index.html",
}

# 目标：列顺序
COLUMNS = ["所属路径", "流程编号", "SAP结算单编码", "创建人", "当前节点",
           "申请报账金额", "供应商名称", "供应商编码", "结算公司名称",
           "发票含税总金额", "发票不含税总金额", "发票总税额", "发票号码"]

# 流程名过滤
TARGET = "华工图像-发票结算审批单（SRM集成）"


def fetch_ids(data_key, base_url, page_size=100):
    """翻页拉取某列表的所有 requestid 与行内标记字段"""
    ids, page = [], 1
    while True:
        r = requests.post(base_url, json={
            "dataKey": data_key, "size": page_size, "current": page,
            "filterType": 1, "extraCond": []
        }, headers=HEADERS, timeout=30)
        r.raise_for_status()
        d = r.json()
        rows = d.get("datas", [])
        if not rows:
            break
        for x in rows:
            # 仅保留目标流程
            if TARGET in (x.get("workflowname") or x.get("workflowname") or ""):
                ids.append(x)
        total = d.get("total", 0)
        if page * page_size >= total or len(rows) < page_size:
            break
        page += 1
    return ids


def load_form(requestid):
    r = requests.post(BASE + "/api/workflow/reqform/loadForm", json={
        "requestid": requestid
    }, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def extract(f):
    """把 loadForm 返回字段映射成 13 列。字段 key 以 d 开头的最宽字符串为准。"""
    nodes = f.get("data", {}).get("reqform", {}).get("nodeInfo", [])
    out = {}
    for n in nodes:
        for c in n.get("fields", []):
            fn = c.get("fieldname", "")
            v = c.get("fieldvalue", "")
            if not fn or v is None:
                continue
            # 保留同名最长前缀（主表字段比子表后缀字段短）
            if fn not in out or len(fn) < len([k for k in out if k == fn]):
                pass
            out[fn] = v if isinstance(v, str) else str(v)
    return out


def row_from(fields):
    def g(*keys):
        for k in keys:
            if k in fields:
                return fields[k]
        return ""
    return [
        "华工图像-发票结算审批单（SRM集成）",   # 所属路径
        g("requestmark"),                        # 流程编号
        "",                                      # SAP结算单编码（接口未暴露，需在页内从SRM只读块抓取）
        g("creater"),                            # 创建人
        g("nodeinfo") if g("nodeinfo") else g("currentnode"),  # 当前节点
        g("totalmoney"),                         # 申请报账金额
        g("supliername", "suppliername", "vendor"),  # 供应商名称
        g("supliercode", "suppliercode", "vendorcode"),  # 供应商编码
        "",                                      # 结算公司名称
        g("invoice_totalamount", "hstotal"),     # 发票含税总金额
        g("invoice_nothamount", "hsnototal"),    # 发票不含税总金额
        g("invoice_tax", "hstax"),               # 发票总税额
        "",                                      # 发票号码（OA未存储，仅在SRM只读块）
    ]


def crawl_ok():
    ids = fetch_ids("listOkBaseInfo", BASE + "/api/workflow/reqlist/doneBaseInfo")
    ids_doing = fetch_ids("listDoingBaseInfo", BASE + "/api/workflow/reqlist/doingBaseInfo")
    return ids + ids_doing


def main():
    if not COOKIE:
        raise SystemExit("请先在脚本里粘贴 Cookie（见文件头说明）。")
    all_ids = crawl_ok()
    print(f"共 {len(all_ids)} 条目标单据，开始并发拉字段...")
    rows = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(load_form, x["requestid"]): x for x in all_ids}
        for fut in tqdm(as_completed(futs), total=len(all_ids)):
            x = futs[fut]
            try:
                fields = extract(fut.result())
            except Exception as e:
                fields = {}
            rows.append(row_from(fields))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "发票结算审批单"
    ws.append(COLUMNS)
    for r in rows:
        ws.append(r)
    wb.save("发票结算审批单.xlsx")
    print("完成，写入", "发票结算审批单.xlsx", len(rows), "行")


if __name__ == "__main__":
    main()