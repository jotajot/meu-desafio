# Gera artigo/img/evolucao-desempenho.png a partir de diagnostico/11-medianas.txt.
#
# Uso (na raiz do repositório; precisa de matplotlib):
#   python3 diagnostico/medianas.py > diagnostico/11-medianas.txt
#   python3 artigo/img/grafico.py
# Sem matplotlib instalado, pelo Docker:
#   docker run --rm -v "$PWD":/repo -w /repo python:3.12-slim \
#     sh -c "pip install -q matplotlib && python artigo/img/grafico.py"
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

ORDEM = [
    ('00-linha-de-base', '00\nbase', 'base'),
    ('01-pool-conexoes', '01\npool', 'mantida'),
    ('02-remover-log-resposta', '02\nlog', 'mantida'),
    ('03-indices-btree', '03\nB-Tree', 'mantida'),
    ('04-indice-trigramas', '04\ntrigramas', 'descartada'),
    ('05-eliminar-n-mais-1', '05\nN+1', 'mantida'),
    ('06-agregacao-sql-vendas-por-dia', '06\nSQL', 'mantida'),
    ('07-indice-criado-em', '07\ndata', 'mantida'),
    ('08-mv-top-produtos', '08\nMV top', 'mantida'),
    ('09-mv-vendas-por-dia', '09\nMV vendas', 'mantida'),
    ('10-otimizar-pedidos-status', '10\n/pedidos', 'mantida'),
    ('10b-remedicao-estado-10', '10b\nremedição', 'remedicao'),
    ('11-cache-busca-produtos', '11\ncache', 'descartada'),
    ('12-gin-busca-sobre-10', '12\ntrigramas', 'mantida'),
    ('13-banco-meia-cpu', '13\n0,5 CPU', 'recomendada'),
]
ROTULAR = {'00-linha-de-base', '10-otimizar-pedidos-status', '10b-remedicao-estado-10',
           '12-gin-busca-sobre-10', '13-banco-meia-cpu'}

AZUL, LARANJA, CINZA, CINZA_CLARO = '#2a78d6', '#eb6834', '#8a8984', '#c9c8c2'
TEXTO, TEXTO_2, GRADE = '#0b0b0b', '#52514e', '#e6e5e0'
ESTILO = {
    'base': dict(color=CINZA, hatch=None),
    'mantida': dict(color=AZUL, hatch=None),
    'descartada': dict(color=CINZA_CLARO, hatch='///'),
    'remedicao': dict(color=CINZA_CLARO, hatch=None),
    'recomendada': dict(color=LARANJA, hatch=None),
}

med = {}
for linha in open('diagnostico/11-medianas.txt', encoding='utf-8'):
    p = linha.split()
    if len(p) == 10 and re.match(r'\d', p[0]):
        med[p[0]] = {'rps': float(p[2]), 'cpu_req': float(p[9])}


def br(v):
    return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'text.color': TEXTO,
                     'axes.labelcolor': TEXTO_2, 'xtick.color': TEXTO_2, 'ytick.color': TEXTO_2})
fig, eixos = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True, gridspec_kw={'hspace': 0.28})
x = range(len(ORDEM))
paineis = [('rps', 'Vazão (req/s, mediana de 3 execuções, escala log): maior é melhor'),
           ('cpu_req', 'CPU gasta por requisição (ms, banco + API, escala log): menor é melhor')]
for ax, (chave, titulo) in zip(eixos, paineis):
    valores = [med[r][chave] for r, _, _ in ORDEM]
    for i, ((rotulo, _, status), v) in enumerate(zip(ORDEM, valores)):
        e = ESTILO[status]
        ax.bar(i, v, width=0.72, color=e['color'], hatch=e['hatch'], edgecolor='white', linewidth=1.5, zorder=2)
        if rotulo in ROTULAR:
            ax.annotate(br(v), (i, v), xytext=(0, 3), textcoords='offset points', ha='center', va='bottom',
                        fontsize=8.5, color=TEXTO)
    ax.set_yscale('log')
    ax.set_title(titulo, loc='left', fontsize=10.5, color=TEXTO, pad=8)
    ax.grid(axis='y', color=GRADE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for lado in ('top', 'right', 'left'):
        ax.spines[lado].set_visible(False)
    ax.spines['bottom'].set_color(CINZA_CLARO)
    ax.tick_params(axis='y', length=0)
    ax.tick_params(axis='x', length=0)
    ax.yaxis.set_major_locator(LogLocator(base=10))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:,.0f}'.replace(',', '.') if v >= 1 else f'{v:g}'.replace('.', ',')))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.margins(y=0.18)
eixos[-1].set_xticks(list(x))
eixos[-1].set_xticklabels([n for _, n, _ in ORDEM], fontsize=8)
eixos[-1].tick_params(axis='x', length=0)

legenda = [Patch(facecolor=CINZA, label='Linha de base'),
           Patch(facecolor=AZUL, label='Mudança mantida'),
           Patch(facecolor=CINZA_CLARO, hatch='///', edgecolor='white', label='Mudança descartada (revertida)'),
           Patch(facecolor=CINZA_CLARO, label='Remedição do estado 10 (sem mudança)'),
           Patch(facecolor=LARANJA, label='Configuração recomendada (banco com 0,5 CPU)')]
fig.legend(handles=legenda, loc='upper center', ncol=3, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 0.995))
fig.text(0.01, 0.005,
         'Fonte: diagnostico/11-medianas.txt (scripts/medir.sh, VUS=20, 60 s, semente 42). '
         '10b, 12 e 13 medidos em 17/11; os demais entre 12 e 15/11.\n'
         'CPU por requisição = (CPU banco % + CPU API %) × 10 ÷ req/s.',
         fontsize=7.5, color=TEXTO_2)
fig.subplots_adjust(left=0.06, right=0.99, top=0.89, bottom=0.13)
fig.savefig('artigo/img/evolucao-desempenho.png', dpi=150, facecolor='white')
print('ok: artigo/img/evolucao-desempenho.png')
