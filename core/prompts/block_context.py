"""Page-local role prompts and eleven fictional examples in the OSS protocol."""
from __future__ import annotations
from dataclasses import replace
import json
from core.prompts.task import TaskPrompt
from core.services.prompt_policy import DEFAULT_PROMPT_POLICY

PROMPT_VERSION = "block-context-oss-v1"

SYSTEMS = {'text': '당신의 Task는 전체 페이지 이미지를 참고하여 일차적으로 추출된 텍스트 블록을 자연스러운 Markdown으로 복원하는 것입니다.\n'
         '\n'
         '### 일차적으로 파싱된 텍스트는 다음과 같이 불완전할 수 있습니다.\n'
         '1. 대제목, 소제목, bullet, 번호 목록, 들여쓰기 형식이 없습니다.\n'
         '2. 취소선과 강조가 표현되어 있지 않습니다.\n'
         '3. 다른 문단이나 표, 이미지와 연결된 정보가 없습니다.\n'
         '4. 글자색으로 나타낸 범례 의미가 없습니다.\n'
         '\n'
         '### 주의 사항\n'
         '* 입력 블록의 내용만 복원하고 페이지 전체를 다시 작성하지 마세요.\n'
         '* 이미지에서 보이는 제목·목록 계층을 사용하고 원문 번호와 순서를 유지하세요.\n'
         '* 취소선이 보이는 부분은 ~~원문~~으로 표현하세요.\n'
         '* 색상이 명시된 범례와 대응하면 (변경 전), (변경 후)처럼 의미를 표시하세요.\n'
         '* 화살표로 연결된 정보는 필요한 경우 짧은 괄호 설명으로 덧붙이세요.\n'
         '* 숫자·단위·고유명사·부정 표현을 임의로 고치거나 문장을 요약하지 마세요.\n'
         '* 확실하지 않은 형식·범례·연결은 추측하지 말고 원문을 유지하세요.',
 'table': '당신의 Task는 전체 페이지 이미지를 참고하여 이미 파싱된 테이블 블록에 빠진 문맥을 복원하는 것입니다.\n'
          '\n'
          '### 테이블에서 복원할 정보\n'
          '1. 표 밖에 있는 단위, 범례, 연결된 짧은 주석.\n'
          '2. 특정 항목의 취소선이나 범례에 따른 색상 의미.\n'
          '3. 본문·이미지와 화살표로 연결된 정보.\n'
          '4. 표 위나 주변에 겹쳐 표시된 부가 설명.\n'
          '5. 다른 색·굵기의 테두리, 배경색 등으로 강조된 열·행·개별 셀.\n'
          '\n'
          '### 주의 사항\n'
          '* 표는 이미 파싱되어 placeholder와 header/first_row/last_row 요약으로 주어집니다.\n'
          '* 절대 이미지에서 표를 다시 파싱하거나 행·열·셀 값을 다시 만들지 마세요.\n'
          '* 입력 placeholder와 요약은 글자 그대로 유지하세요. 없는 placeholder를 생성하지 마세요.\n'
          '* 요약에 없는 중간 행은 생략된 것입니다. 원본 표에 없다고 판단하지 마세요.\n'
          '* 추가 문맥만 placeholder와 요약 뒤에 짧은 문장이나 괄호 설명으로 붙이세요.\n'
          '* 특정 셀의 표시를 설명할 때는 읽을 수 있는 행 이름·열 이름·값을 명시하세요.\n'
          '* 테두리 강조는 색·굵기와 강조 범위를 표 하단에 설명하세요. 열 전체인지 헤더만인지 일부 셀인지 구분하세요.\n'
          '* 표 전체의 외곽선이나 일반 격자선은 특정 항목 강조로 해석하지 마세요.\n'
          '* 강조의 의미는 범례나 본문에 명시된 경우에만 붙이세요. 근거 없이 중요·선택·승인 같은 상태를 추측하지 마세요.\n'
          '* 셀이나 연결이 확실하지 않으면 그 부분은 추가하지 마세요.\n'
          '* 복원할 정보가 없으면 입력 텍스트를 그대로 반환하세요.',
 'image': '당신의 Task는 전체 페이지 이미지를 참고하여 일차적으로 파싱된 이미지 블록에 빠진 문맥을 복원하는 것입니다.\n'
          '\n'
          '### 이미지에서 복원할 정보\n'
          '1. 주변 본문·표·다른 이미지와 화살표로 연결된 정보.\n'
          '2. 외부 범례에 따른 색상 의미.\n'
          '3. 이미지 위에 겹쳐 표시된 문구나 직접 연결된 짧은 주석.\n'
          '\n'
          '### 주의 사항\n'
          '* 이미지 링크와 기존 설명, caption 시작·끝 태그는 그대로 유지하세요.\n'
          '* 이미지 자체를 처음부터 다시 설명하거나 기존 설명을 고치지 마세요.\n'
          '* 추가 문맥만 기존 이미지 블록 뒤에 짧은 문장이나 괄호 설명으로 붙이세요.\n'
          '* caption 태그가 있다면 추가 문맥은 태그 바깥에 붙이세요.\n'
          '* 주변 표 전체, 가격, 도면 치수, 차트 수치를 다시 파싱하지 마세요.\n'
          '* 보이는 화살표 연결을 설명하되 인과·가격 대응·시간 순서를 추측하지 마세요.\n'
          '* 색상 의미는 명시된 범례를 따르고 불확실한 연결은 추가하지 마세요.\n'
          '* 기존 설명에 이미 있는 내용을 반복하지 마세요.\n'
          '* 복원할 정보가 없으면 입력 텍스트를 그대로 반환하세요.'}

EXAMPLES = {'text': [{'image_fixture': '페이지 범례는 검정=변경 전, 파랑=변경 후다. 대상 첫 줄은 소제목이고 아래 두 문장은 bullet이며 각각 검정·파랑이다.',
           'input': '1. 냉방 시설 확충\n책상 위에 각각 개인별 선풍기 설치 필요\n그냥 에어컨 설치하기로 함',
           'response': {'reasoning': '소제목과 목록 형식을 복원하고 범례에 따라 변경 전·후를 표시했습니다.',
                        'output': '### 1. 냉방 시설 확충\n'
                                  '* (변경 전) 책상 위에 각각 개인별 선풍기 설치 필요\n'
                                  '* (변경 후) 그냥 에어컨 설치하기로 함'}},
          {'image_fixture': '일정표 아래 설명은 bullet 두 줄이며 첫 문장의 동우기획에만 취소선이 있다.',
           'input': '홍보는 동우기획에서 진행한다.\n홍보반응 조사는 상혁리서치에서 진행한다.',
           'response': {'reasoning': '목록 형식을 복원하고 동우기획의 취소선을 반영했습니다.',
                        'output': '* 홍보는 ~~동우기획~~에서 진행한다.\n* 홍보반응 조사는 상혁리서치에서 진행한다.'}},
          {'image_fixture': '앞 블록의 1·2 다음에 3·4가 이어진다. 주간 단위 확인은 3의 하위 bullet이다. 3에서 4로 화살표가 연결된다. 결과 공유는 '
                            '파란색이지만 범례 글씨는 읽을 수 없다.',
           'input': '3. 일정 확인\n주간 단위 확인\n4. 결과 공유',
           'response': {'reasoning': '목록과 화살표 연결은 복원했지만 파란색의 범례 의미는 판독하지 못했습니다.',
                        'output': '3. 일정 확인\n   * 주간 단위 확인\n4. 결과 공유\n\n(일정 확인에서 결과 공유로 화살표가 연결됨)'}}],
 'table': [{'image_fixture': '중앙 모델 양옆에 의상 표가 있다. 대상 표에서 모델의 발로 화살표가 연결되고, 대상 표에 붙은 말풍선에는 양말은 편해야 한다라고 적혀 '
                             '있다.',
            'input': '[[TABLE_BLOCK:table_5ae125bf654b52af]]\n'
                     'header: 의상 | 가격\n'
                     'first_row: 양말 | 500\n'
                     'last_row: 신발 | 1000',
            'response': {'reasoning': '모델의 발과 연결된 화살표 및 표에 붙은 주석을 추가했습니다.',
                         'output': '[[TABLE_BLOCK:table_5ae125bf654b52af]]\n'
                                   'header: 의상 | 가격\n'
                                   'first_row: 양말 | 500\n'
                                   'last_row: 신발 | 1000\n'
                                   '\n'
                                   '(중앙 모델 이미지의 발 영역으로 화살표가 연결됨)\n'
                                   '* 표에 연결된 주석: 양말은 편해야 한다.'}},
           {'image_fixture': '중간 행 홍보의 일정 열에서 검정색 25년 10월에 취소선이 있고 파란색 25년 11월이 보인다. 두 값은 원본 표에도 있다. 범례는 '
                             '검정=기존 일정/파랑=변경 일정이다.',
            'input': '[[TABLE_BLOCK:table_53c50ae1dbff4644]]\n'
                     'header: 구분 | 일정\n'
                     'first_row: 기획 | 25년 1월\n'
                     'last_row: 홍보 반응 조사 | 25년 12월',
            'response': {'reasoning': '홍보 일정의 취소선과 범례에 따른 기존·변경 일정을 표 뒤에 설명했습니다.',
                         'output': '[[TABLE_BLOCK:table_53c50ae1dbff4644]]\n'
                                   'header: 구분 | 일정\n'
                                   'first_row: 기획 | 25년 1월\n'
                                   'last_row: 홍보 반응 조사 | 25년 12월\n'
                                   '\n'
                                   '(홍보 행의 일정 열: 25년 10월은 취소선이 표시된 기존 일정이며, 25년 11월은 변경 일정임)'}},
           {'image_fixture': '대상 표 바로 위에 단위: 백만원이 있다. 중간 행에 취소선처럼 보이는 표시가 있지만 행 이름과 숫자는 읽을 수 없다.',
            'input': '[[TABLE_BLOCK:table_7cf854ce931e3d8d]]\n'
                     'header: 부문 | 매출\n'
                     'first_row: 국내 | 120\n'
                     'last_row: 해외 | 80',
            'response': {'reasoning': '단위는 추가했지만 중간 행의 취소선 대상은 판독하지 못했습니다.',
                         'output': '[[TABLE_BLOCK:table_7cf854ce931e3d8d]]\n'
                                   'header: 부문 | 매출\n'
                                   'first_row: 국내 | 120\n'
                                   'last_row: 해외 | 80\n'
                                   '\n'
                                   '(단위: 백만원)'}},
           {'image_fixture': '기존안과 항목 열은 얇은 회색 격자선이다. 변경안 열은 헤더부터 마지막 행까지 굵은 빨간색 테두리로 둘러싸여 있다. 강조 의미를 설명하는 '
                             '범례나 본문은 없다.',
            'input': '[[TABLE_BLOCK:table_13d0e928d1a0010a]]\n'
                     'header: 항목 | 기존안 | 변경안\n'
                     'first_row: 냉방 | 선풍기 | 에어컨\n'
                     'last_row: 조명 | 형광등 | LED',
            'response': {'reasoning': '변경안 열 전체의 빨간색 테두리 강조를 표 하단에 설명했습니다.',
                         'output': '[[TABLE_BLOCK:table_13d0e928d1a0010a]]\n'
                                   'header: 항목 | 기존안 | 변경안\n'
                                   'first_row: 냉방 | 선풍기 | 에어컨\n'
                                   'last_row: 조명 | 형광등 | LED\n'
                                   '\n'
                                   '(강조 표시: 변경안 열 전체가 헤더부터 마지막 행까지 굵은 빨간색 테두리로 둘러싸여 있음)'}},
           {'image_fixture': '국내 행의 매출 120 셀만 굵은 파란색 테두리로 둘러싸여 있다. 매출 헤더와 해외 행의 80 셀은 일반 회색 격자선이다. 표 옆 범례는 '
                             '파란색 테두리: 검토 대상이라고 명시한다.',
            'input': '[[TABLE_BLOCK:table_df0cbe97416d7eb6]]\n'
                     'header: 부문 | 매출\n'
                     'first_row: 국내 | 120\n'
                     'last_row: 해외 | 80',
            'response': {'reasoning': '국내 매출 셀의 테두리 강조와 범례의 검토 대상 의미를 표 하단에 추가했습니다.',
                         'output': '[[TABLE_BLOCK:table_df0cbe97416d7eb6]]\n'
                                   'header: 부문 | 매출\n'
                                   'first_row: 국내 | 120\n'
                                   'last_row: 해외 | 80\n'
                                   '\n'
                                   '(강조 표시: 국내 행의 매출 열, 120 셀만 굵은 파란색 테두리로 둘러싸여 있으며 범례상 검토 대상임)'}}],
 'image': [{'image_fixture': '발은 양말·신발 표와, 머리는 모자·선글라스 표와 화살표로 연결된다. 모자 위에는 모자에 EDGE 있는 장식 포인트! 문구가 겹쳐 있다.',
            'input': '![모델_이미지](모델_이미지.png)\n'
                     '\n'
                     '```vlm_image_caption\n'
                     '중앙에 패션 모델이 서 있으며 모자와 양말, 신발을 착용하고 있다.\n'
                     '```\n',
            'response': {'reasoning': '의상 표와의 연결 및 모자 위 오버레이 문구를 추가했습니다.',
                         'output': '![모델_이미지](모델_이미지.png)\n'
                                   '\n'
                                   '```vlm_image_caption\n'
                                   '중앙에 패션 모델이 서 있으며 모자와 양말, 신발을 착용하고 있다.\n'
                                   '```\n'
                                   '\n'
                                   '\n'
                                   '(발은 양말·신발 항목의 의상 표와, 머리는 모자·선글라스 항목의 의상 표와 화살표로 연결됨)\n'
                                   '* 모자에 EDGE 있는 장식 포인트!'}},
           {'image_fixture': '선풍기 표시는 검정, 에어컨 표시는 파랑이다. 그림 옆 범례는 검정=변경 전/파랑=변경 후다.',
            'input': '![사무실_배치](사무실_배치.png)\n\n```vlm_image_caption\n책상 옆 선풍기와 벽면 에어컨의 위치가 표시되어 있다.\n```\n',
            'response': {'reasoning': '그림 옆 범례에 따라 선풍기와 에어컨 표시의 의미를 추가했습니다.',
                         'output': '![사무실_배치](사무실_배치.png)\n'
                                   '\n'
                                   '```vlm_image_caption\n'
                                   '책상 옆 선풍기와 벽면 에어컨의 위치가 표시되어 있다.\n'
                                   '```\n'
                                   '\n'
                                   '\n'
                                   '(범례상 검정색 선풍기 표시는 변경 전, 파란색 에어컨 표시는 변경 후를 뜻함)'}},
           {'image_fixture': '모델의 발에서 선이 나가지만 두 표 중 어느 표에 도착하는지는 겹쳐서 읽을 수 없다. 다른 확실한 추가 문맥은 없다.',
            'input': '![모델_이미지](모델_이미지.png)\n\n```vlm_image_caption\n중앙에 패션 모델이 서 있다.\n```\n',
            'response': {'reasoning': '화살표의 연결 대상을 판독할 수 없어 기존 이미지 블록을 유지했습니다.',
                         'output': '![모델_이미지](모델_이미지.png)\n'
                                   '\n'
                                   '```vlm_image_caption\n'
                                   '중앙에 패션 모델이 서 있다.\n'
                                   '```\n'}}]}

OUTPUT_RULES = ('### 답변 형식\n'
 '다음 두 문자열만 가진 JSON으로 답변하세요.\n'
 '{\n'
 '  "reasoning": "복원한 내용이나 판독 한계를 한 문장으로 짧게 설명",\n'
 '  "output": "복원한 블록 텍스트"\n'
 '}\n'
 'JSON 바깥 설명이나 코드펜스는 출력하지 마세요.\n'
 '복원할 정보가 없으면 output에 입력 텍스트를 그대로 반환하세요.\n'
 '확인할 수 없는 정보는 추측하지 말고 원문을 유지하세요.\n'
 '판독 한계가 있으면 reasoning에 짧게 언급하고 output에 검토용 문구를 넣지 마세요.')

RESPONSE_SCHEMA = {'type': 'object',
 'properties': {'reasoning': {'type': 'string'}, 'output': {'type': 'string'}},
 'required': ['reasoning', 'output'],
 'additionalProperties': False}


def build_block_context_prompt(block_kind, block_text, *, block_id=None, user_prompt=None,
                               few_shot_examples=(1, 2), policy=DEFAULT_PROMPT_POLICY):
    if block_kind not in EXAMPLES:
        raise ValueError("unknown block restoration role")
    available = EXAMPLES[block_kind]
    if (len(few_shot_examples) > 2 or len(set(few_shot_examples)) != len(few_shot_examples)
            or any(type(i) is not int or not 1 <= i <= len(available) for i in few_shot_examples)):
        raise ValueError("select zero to two distinct examples available for the role")
    system = SYSTEMS[block_kind] + "\n\n" + OUTPUT_RULES
    if few_shot_examples:
        system += "\n\n다음은 가상 이미지 조건을 가진 예시입니다. 현재 페이지의 사실이 아닙니다."
        for index in few_shot_examples:
            system += "\n\n" + json.dumps(available[index - 1], ensure_ascii=False)
    return replace(TaskPrompt.build(
        "BLOCK_CONTEXT_" + block_kind.upper(), system,
        {"block_kind": block_kind, "block_id": block_id, "reference": block_text},
        user_prompt=user_prompt, policy=policy,
    ), version=PROMPT_VERSION)
