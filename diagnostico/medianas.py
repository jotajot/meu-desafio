# Calcula a mediana de cada métrica entre as execuções de cada rótulo em resultados/
# e a CPU gasta por requisição (métrica derivada, não gerada pelo medir.sh).
#
# Uso (na raiz do repositório):
#   python3 diagnostico/medianas.py > diagnostico/11-medianas.txt
#
# Só lê resultados/*/resumo.txt e resultados/*/recursos.txt; não altera nada.
import glob
import re
import statistics as st
from collections import defaultdict

grupos = defaultdict(list)
for pasta in sorted(glob.glob('resultados/*/')):
    rotulo = re.sub(r'^\d{8}-\d{6}-', '', pasta.rstrip('/').split('/')[-1])
    resumo = open(pasta + 'resumo.txt', encoding='utf-8').read()
    recursos = open(pasta + 'recursos.txt', encoding='utf-8').read()

    rps = float(re.search(r'Requisições/s:\s+([\d.]+)', resumo).group(1))
    p95 = float(re.search(r'p95 ([\d.]+) ms', resumo).group(1))
    cpu_b, ram_b = map(float, re.search(r'banco-1\s+\d+\s+([\d.]+)%\s+[\d.]+%\s+([\d.]+) MiB', recursos).groups())
    cpu_a, ram_a = map(float, re.search(r'api-1\s+\d+\s+([\d.]+)%\s+[\d.]+%\s+([\d.]+) MiB', recursos).groups())

    # 100% = 1 CPU = 1.000 ms de CPU por segundo; dividido por req/s = ms de CPU por requisição.
    cpu_ms_req_b = cpu_b * 10 / rps
    cpu_ms_req = (cpu_b + cpu_a) * 10 / rps
    grupos[rotulo].append((rps, p95, cpu_b, cpu_a, ram_b, ram_a, cpu_ms_req_b, cpu_ms_req))

print('Mediana calculada métrica a métrica entre as execuções de cada rótulo')
print('(req/s e p95 de uma mesma linha podem vir de execuções diferentes).')
print('cpu_ms_req_banco = CPU banco % x 10 / req/s')
print('cpu_ms_req_total = (CPU banco % + CPU API %) x 10 / req/s')
print('As duas são calculadas por execução e depois tira-se a mediana.')
print('ram_* = memória média do container (inclui cache de páginas; varia entre execuções).')
print()
print(f"{'rotulo':34} {'n':>2} {'req/s':>8} {'p95_ms':>9} {'cpu_b%':>7} {'cpu_a%':>7} "
      f"{'ram_b_MiB':>9} {'ram_a_MiB':>9} {'cpu_ms_req_banco':>16} {'cpu_ms_req_total':>16}")
for rotulo, execucoes in sorted(grupos.items()):
    m = [st.median(valores) for valores in zip(*execucoes)]
    print(f"{rotulo:34} {len(execucoes):>2} {m[0]:8.2f} {m[1]:9.1f} {m[2]:7.1f} {m[3]:7.1f} "
          f"{m[4]:9.1f} {m[5]:9.1f} {m[6]:16.2f} {m[7]:16.2f}")
