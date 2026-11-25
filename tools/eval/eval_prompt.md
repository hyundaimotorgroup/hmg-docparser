# Evaluation prompt and code excerpt

[Evaluation setup and scoring](README.md) · [한국어 안내](../../docs/kor/evaluation.md)

We used `gpt-5.4-mini` as the evaluation LLM. This is a code excerpt, not a
standalone runner: supply a judge callable, retry/timeout imports, page/fact
pairing, and result collection. Verify every expected fact has a valid judgment
before aggregating; the example counts supplied judgments only. Parse model
responses safely rather than executing them. See the evaluation guide for data
rights, provider costs, and reproducibility requirements.

## Evaluation intent and few-shot design

The prompt was designed to assess both recall and precision in document parsing: whether the parsed document preserves the expected facts, and whether it introduces incorrect or contradictory information. The few-shot examples accept facts supported by reasonable inference or optional configurations, while rejecting missing evidence, incompatible values, and contradictions between prose and tables. They also teach the evaluator to respect table structure: a marker in another row does not support the target fact, and an empty schedule cell must not be interpreted as a positive entry. These cases aim to detect contradictory facts and unsupported inferences while allowing minor numerical differences and facts that do not require an exact wording match.

Examples 1 and 5 target incompatible values and internal contradictions; Example 2 targets missing evidence; Examples 3 and 4 allow optional configurations and supported inference; and Examples 6 and 7 guard against incorrect interpretations of empty cells and markers belonging to other rows in Markdown and HTML tables. This design addresses both recall and precision, although the aggregation code below reports the proportion of facts judged `True`, rather than computing separate recall and precision metrics.

## English translation of the evaluation prompt

The translation below preserves the original examples, values, placeholders, and Python f-string brace escaping. The output keys `이유` (reason) and `결과` (result) are retained to match the original response schema.

````text
- If the Fact can be inferred, it is True even if it does not match the document exactly. Also, for time or numerical values, small differences at the decimal level should be allowed.
- In Gantt charts or schedule tables (rows: items, columns: periods), an empty cell means that the corresponding item is absent during that period. Only cells with explicit markings such as ●, ■, O, ▶, shading, or a bar should be considered to include the item during that period. Never infer that an item applies to a particular period from an empty cell.

Output True if true, and False if false.
The output must follow the Python dict format.

>>> Example
(Fact)
The T-shirt is available only in sizes L and M.

(Document)
| Product | Price | Size |
| ------ |------ | ------ |
| T-shirt | 59,000 | L,M,S |
| Pants | 39,000 | 105 |

(Example output)
{{"이유": "The Fact states that the T-shirt is available only in sizes L and M, but the given document lists L,M,S. The given document is incorrect.",
"결과": False}}


>>> Example 2
(Fact)
Euclidean distance is a representative method for measuring distances between sentences.

(Document)
A method for defining the morphological similarity between strings, such as words or sentences, is called string distance. Levenshtein distance, also known as edit distance, is one of the representative string distance metrics.

(Example output)
{{"이유": "The Fact describes Euclidean distance, but this cannot be found in the document.",
"결과": False}}


>>> Example 3
(Fact)
The assorted fruit gift set includes two pears.

(Document)
Assorted fruit gift set: two apples included by default
You may freely choose the desired configuration from the following:
- Two pears, two bunches of grapes, two bananas

(Example output)
{{"이유": "The assorted fruit gift set does not necessarily include two pears, but two pears can be included as an option. Therefore, it is True.",
"결과": True}}


>>> Example 4
(Fact)
An electric vehicle's driving range may decrease when the weather gets colder.

(Document)
In below-freezing weather, battery density decreases, which may affect the vehicle's driving range.

(Example output)
{{"이유": "The document's contents allow us to infer that an electric vehicle's driving range may decrease.",
"결과": True}}


>>> Example 5
(Fact)
The Hyundai Sonata has an overall length of 5000 cm.

(Document)
The Hyundai Sonata has an overall length of 5000 cm.
| Model | Overall length |
| --- | --- |
| Sonata | 4950 |
| Grandeur | 5010 |


(Example output)
{{"이유": "Some content in the document contradicts the fact. The overall length is incorrectly stated in the table.",
"결과": False}}

>>> Example 6
(Fact)
Pollock can be caught from March to May.

(Document)
| Fish species | January | February | March | April |
| --- | --- | --- | --- | --- |
| Pollock | | | | |
| Squid | | | O | |
| Red sea bream | O | O | O | O |

(Example output)
{{"이유": "In the table, the March–May cells in the pollock row are empty. Even if cells for other species (squid and red sea bream) contain O markings, information about pollock cannot be confirmed when the pollock row is empty, so the result is False. Empty cells must not be interpreted as indicating a possibility without evidence.",
"결과": False}}


>>> Example 7
(Fact)
Red sea bream can be caught in March.

(Document)
<table>
<thead>
<tr><th>Fish species</th><th>January</th><th>February</th><th>March</th><th>April</th></tr>
</thead>
<tbody>
<tr><td>Pollock</td><td></td><td></td><td></td><td></td></tr>
<tr><td>Squid</td><td></td><td></td><td>O</td><td></td></tr>
<tr><td>Red sea bream</td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>

(Example output)
{{"이유": "The March cell in the red sea bream row is empty. The March cell in the squid row contains O, but this is information about squid and is unrelated to red sea bream. Information that is not explicitly stated in the table cannot be judged as possible, so the result is False.",
"결과": False}}


Now determine whether the given document and Fact agree.
※Caution※ Do not output Markdown tags such as ```; output only a Python dict.

(Fact)
{fact}

(Document)
{text}

(Output)
````

## Original evaluation code

```python
@retry(retry=retry_if_exception_type(ReadTimeout) | retry_if_exception_type(ConnectTimeout), stop=stop_after_attempt(100), wait=wait_fixed(5))
def judge_fact_from_text(fact, text, llm=llm):
    prompt = f"""다.
- 문서와 완벽히 일치하지 않더라도 Fact를 추론해낼 수 있으면 True다. 또한 시점이나 수와 관련된 경우 소수점 단위의 작은 오차는 허용해야 한다.
- 간트차트나 일정표 형식의 표(행: 항목, 열: 기간)에서 셀이 비어 있으면 해당 기간에 해당 항목이 없음을 의미한다. 표에 ●, ■, O, ▶, 색칠, 바(bar) 등 명시적 표기가 있는 셀만 해당 기간에 포함된 것으로 판단한다. 비어 있는 셀을 보고 특정 기간에 해당한다고 추론해서는 절대 안 된다.

참이면 True를 출력하고, 거짓이면 False를 출력하라.
출력은 python dict 형태를 따른다.

>>> 예시
(Fact)
티셔츠 크기는 L,과 M 사이즈만 있다.

(문서)
| 제품명 | 가격 | 크기 |
| ------ |------ | ------ |
| 티셔츠 | 59,000 |   L,M,S  |
| 바지 | 39,000 |   105   |

(출력예시)
{{"이유": "Fact에서는 티셔츠 크기가 L과 M만 있다고 했지만 주어진 문서에서는 L,M,S 라 써져있다. 주어진 문서가 틀렸다.",
"결과": False}}


>>> 예시 2
(Fact)
유클리디언 디스턴스는 대표적인 문장 거리 측정 기법이다.

(문서)
단어, 혹은 문장과 같은 string 간의 형태적 유사성을 정의하는 방법을 string distance 라 합니다. Edit distance 라는 별명을 지닌 Levenshtein distance 는 대표적인 string distance metric 중 하나입니다.

(출력예시)
{{"이유": "Fact는 유클리디언 거리를 설명하고 있는데, 문서에서는 이를 찾을 수 없다.",
"결과": False}}


>>> 예시 3
(Fact)
종합 과일 선물 세트는 배 2개를 포함 한다.

(문서)
종합 과일 선물 세트: 기본 사과 2개
다음 중 필요한 구성을 마음껏 선택할 수 있습니다.
- 배 2개, 포도 2개, 바나나 2개

(출력예시)
{{"이유": "무조건 종합과일 선물세트가 배 2개를 포함하지는 않지만, 선택으로 배 2개를 포함할 수 있다. 그러므로 True다.",
"결과": True}}


>>> 예시 4
(Fact)
추워지면 전기차의 주행거리가 줄어들 수 있다.

(문서)
영하의 날씨에서는 배터리 밀도가 줄어들고 이는 자동차의 주행거리에 영향을 줄 수 있다.

(출력예시)
{{"이유": "문서의 내용을 통해 전기차의 주행거리가 줄어들 수 있다는 것을 추론할 수 있다.",
"결과": True}}


>>> 예시 5
(Fact)
현대 쏘나타의 전장은 5000cm다.

(문서)
현대 쏘나타의 전장은 5000cm다.
| 차종 | 전장 |
| --- | --- |
| 쏘나타 | 4950 |
| 그랜저 | 5010 |


(출력예시)
{{"이유": "문서의 내용 중 사실과 모순되는 부분이 존재한다. 표에서는 전장이 잘못 표기되어 있다.",
"결과": False}}

>>> 예시 6
(Fact)
명태는 3~5월에 잡을 수 있다.

(문서)
| 어종 | 1월 | 2월 | 3월 | 4월 |
| --- | --- | --- | --- | --- |
| 명태 | | | | |
| 오징어 | | | O | |
| 참돔 | O | O | O | O |

(출력예시)
{{"이유": "표에서 명태 행의 3월 ~ 5월 칸은 비어 있다. 다른 어종(오징어, 참돔)의 셀에 O가 표기되어 있더라도, 명태 행이 비어 있으면 명태에 대한 정보는 확인할 수 없으므로 False다. 빈 셀을 근거 없이 가능하다고 추론해서는 안 된다.",
"결과": False}}


>>> 예시 7
(Fact)
참돔은 3월에 잡을 수 있다.

(문서)
<table>
<thead>
<tr><th>어종</th><th>1월</th><th>2월</th><th>3월</th><th>4월</th></tr>
</thead>
<tbody>
<tr><td>명태</td><td></td><td></td><td></td><td></td></tr>
<tr><td>오징어</td><td></td><td></td><td>O</td><td></td></tr>
<tr><td>참돔</td><td></td><td></td><td></td><td></td></tr>
</tbody>
</table>

(출력예시)
{{"이유": "참돔 행의 3월 셀은 비어 있다. 오징어 행의 3월 셀에 O가 있지만 이는 오징어에 대한 정보이며 참돔과 무관하다. 표에 명시되지 않은 정보는 가능하다고 판단할 수 없으므로 False다.",
"결과": False}}



이제 주어진 문서와 Fact 일치 여부를 판단해라.
※주의※ ```와 같은 markdown 태그는 출력하지 말고 오직 python dict만 출력하라.

(Fact)
{fact}

(문서)
{text}

(출력)
"""

    response = llm(prompt)
    response_dict = _safe_parse_judge_response(response)
    return response_dict



external_fact_dict_page_idx = {
    '학사 로드맵': [0, 1],
    '현대자동차 ESG 보고서': [2, 3, 4, 5],
    '한국은행 소득분배 리포트': [6, 7],
    '연구 추진일정': [8, 9, 10],
    '아이오닉5 실내 퓨즈박스': [11],
}

design_fact_dict_page_idx = {
    '디자인평가셋': [0, 1, 2, 3, 4],
}

simple_fact_dict_page_idx = {
    '쉬운 PPT': [0, 1, 2, 3, 4, 5],
    'ebook': [6, 7, 8],
    '오너스매뉴얼': [9, 10, 11, 12],
    '매거진': [13, 14],
    '논문': [15, 16, 17, 18, 19],
}

def calculate_accuracy_stats(ret_dict, fact_dict, fact_dict_page_idx):
    """
    Calculate overall and category-wise accuracy statistics

    Args:
        ret_dict (dict): Dictionary containing results
        fact_dict (dict): Dictionary containing facts
        fact_dict_page_idx (dict): Dictionary containing page ranges for each category

    Returns:
        tuple: (overall_accuracy, category_accuracies)
        where category_accuracies is a list of (category, accuracy, correct_count, total_count) tuples
    """
    # Calculate overall accuracy
    ret_list = list(ret_dict.values())
    overall_accuracy = len([ret for ret in ret_list if ret['결과']]) / len(ret_list)
    print("Overall accuracy:", overall_accuracy)

    # Calculate accuracy by category
    category_stats = []
    for category, page_range in fact_dict_page_idx.items():
        category_results = []
        for page in page_range:
            for fact in fact_dict[page]:
                result = ret_dict.get((page, fact))
                if result:
                    category_results.append(result)

        if category_results:
            correct_count = len([ret for ret in category_results if ret['결과']])
            total_count = len(category_results)
            accuracy = correct_count / total_count
            print(f"{category}: {accuracy:.3f} ({correct_count}/{total_count})")
            category_stats.append((category, accuracy, correct_count, total_count))

    return overall_accuracy, category_stats
```
