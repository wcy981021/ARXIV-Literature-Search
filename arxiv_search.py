# server/arxiv_search.py
# 您已有的代码，但进行了模块化处理
import arxiv
import datetime
import time
import os
import requests
from tqdm import tqdm

def construct_query(keywords, search_mode="precise"):
    """
    按照arXiv API语法构造查询字符串
    
    参数:
    keywords (str): 空格分隔的关键词
    search_mode (str): "precise"(精确) 或 "fuzzy"(模糊)
    
    返回:
    str: 格式正确的查询字符串
    """
    # 分割关键词
    keyword_list = [k.strip() for k in keywords.split() if k.strip()]
    
    if not keyword_list:
        return ""
    
    # 对单个关键词
    if len(keyword_list) == 1:
        if search_mode == "precise":
            return f"(ti:{keyword_list[0]} AND abs:{keyword_list[0]})"
        else:  # fuzzy
            return f"(ti:{keyword_list[0]} OR abs:{keyword_list[0]})"
    
    # 对多个关键词
    query_parts = []
    for keyword in keyword_list:
        if search_mode == "precise":
            # 标题和摘要都必须包含关键词
            query_parts.append(f"(ti:{keyword} AND abs:{keyword})")
        else:  # fuzzy
            # 标题或摘要包含关键词
            query_parts.append(f"(ti:{keyword} OR abs:{keyword})")
    
    # 用AND连接所有部分以确保所有关键词都存在
    return " AND ".join(query_parts)

def search_arxiv(keywords, start_year=None, end_year=None, max_results=100, search_mode="precise"):
    """
    根据关键词和年份范围在arXiv上搜索论文
    
    参数:
    keywords (str): 搜索关键词
    start_year (int): 开始年份(包含)
    end_year (int): 结束年份(包含)
    max_results (int): 最大结果数量
    search_mode (str): "precise"(关键词必须同时在标题和摘要中) 
                      或 "fuzzy"(关键词在标题或摘要中)
    
    返回:
    list: 符合条件的arxiv.Result对象列表
    """
    # 使用arXiv语法构造查询
    query = construct_query(keywords, search_mode)
    
    if not query:
        print("错误: 未提供有效关键词。")
        return []
    
    print(f"使用arXiv查询: {query}")
    
    # 创建搜索客户端，使用适当参数
    client = arxiv.Client(
        page_size=100,  # API允许的最大值
        delay_seconds=3.0,  # 对API友好
        num_retries=3
    )
    
    # 创建搜索
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )
    
    # 获取结果
    print("从arXiv获取数据...")
    try:
        results = list(client.results(search))
        print(f"检索到 {len(results)} 篇论文")
    except Exception as e:
        print(f"检索结果时出错: {str(e)}")
        return []
    
    # 如果指定了年份范围，过滤结果
    if start_year or end_year:
        filtered_results = []
        for paper in results:
            paper_date = paper.published
            paper_year = paper_date.year
            
            if start_year and paper_year < start_year:
                continue
            if end_year and paper_year > end_year:
                continue
                
            filtered_results.append(paper)
        
        print(f"年份过滤后: {len(filtered_results)} 篇论文")
        return filtered_results
    
    return results

def download_papers(papers, download_dir="arxiv_papers"):
    """
    下载论文PDF
    """
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    
    print(f"下载 {len(papers)} 篇论文到 {download_dir} 目录")
    
    for i, paper in enumerate(tqdm(papers, desc="下载论文")):
        pdf_url = paper.pdf_url
        paper_id = paper.entry_id.split('/')[-1]
        safe_title = "".join(c if c.isalnum() else "_" for c in paper.title)[:50]
        filename = f"{paper_id}_{safe_title}.pdf"
        filepath = os.path.join(download_dir, filename)
        
        try:
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # 对服务器友好 - 添加下载间隔
            time.sleep(1)
        except Exception as e:
            print(f"下载 {paper.title} 时出错: {str(e)}")

# 注意：我们移除了main()函数调用，因为这个文件现在是一个模块