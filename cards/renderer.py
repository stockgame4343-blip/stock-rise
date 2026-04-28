"""카드별 입력 dict + 시리즈 컬러 토큰 → HTML 문자열.

Jinja2 사용. base.html.tmpl 이 공통 골격(헤더·푸터·배경)을,
{name}.html.tmpl 이 카드별 콘텐츠를 채움.
"""

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config


CARD_NAMES = ('pre0', 'pre', 'pre2', 'pre3', 'leader', 'leader2', 'close', 'close2')


def _make_env():
    return Environment(
        loader=FileSystemLoader(config.TEMPLATE_DIR),
        autoescape=select_autoescape(['html', 'tmpl']),
        trim_blocks=False,
        lstrip_blocks=False,
    )


_env = _make_env()


def render_card(name, data):
    """카드 1장의 HTML. data가 None이면 None 반환 (스킵)."""
    if data is None:
        return None
    series = data.get('series')
    tokens = config.COLOR_TOKENS.get(series)
    if tokens is None:
        raise ValueError(f"unknown series '{series}' in card '{name}'")
    template = _env.get_template(f'{name}.html.tmpl')
    return template.render(data=data, tokens=tokens)


def render_all(cards):
    """카드 7장 HTML dict. 입력 카드가 None이면 결과도 None."""
    return {name: render_card(name, cards.get(name)) for name in CARD_NAMES}


def write_html(html, name, output_dir, date):
    """렌더된 HTML을 파일로 저장 (PNG 변환 전 중간 산출물)."""
    if html is None:
        return None
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f'{date}-{name}.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path
