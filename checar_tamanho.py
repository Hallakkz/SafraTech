import sys; from pathlib import Path
R=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(R))
from dotenv import load_dotenv; load_dotenv(R/".env")
from modules.eduagro_ai import tutor, deepseek_client as ds
c=ds.obter_cliente(); p=tutor.preparar("Como interpretar o fósforo na análise de solo?","Intermediário",[])
t="".join(tutor.responder_stream(c,p)); r=c.ultima_resposta
open(R/"dados_eduagro"/"checar_tamanho.txt","w",encoding="utf-8").write(f"max_tokens={c.config.max_tokens} fim={r.motivo_fim} saida={r.tokens_saida} chars={len(t)}\n\n"+t[-1500:])
