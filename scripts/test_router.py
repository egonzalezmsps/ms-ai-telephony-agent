import os
from dotenv import load_dotenv
load_dotenv()

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.router.semantic_router import load_reference_embeddings, classify

print("Cargando embeddings de referencia...")
load_reference_embeddings()
print("Listo.\n")

casos = [
    # Casos originales
    "hasta cuando dura esta promocion?",
    "tienes planes mas baratos?",
    "cuantos gigas tengo en mi plan?",
    "como es el proceso para activar?",
    "quiero ver planes ultra",
    "que gano con el cambio?",
    "tienes algo mas economico?",
    "cuando me cobran?",
    "por que tengo que ir al cac?",
    "dame otra recomendacion",
    "quiero mas gigas",
    "tienes planes libre?",
    "quisiera un plan con mayor numero de gigas",
    "quiero ver planes de menor costo",
    "y mas baratos?",
    "hasta cuando aplica esta oferta?",
    "puedo activarlo mañana?",
    "que diferencia hay con mi plan actual?",
    # Casos problemáticos
    "me parece caro",
    "me interesa",
    "pero este plan tiene cashback?",
    "me interesa el libre 5",
    "y en los planes ultra tambien lo obtendria?",
    "quiero evaluar bien los beneficios",
    "solo dije que me interesa",
    "me llama la atencion ese plan",
]

print(f"{'Mensaje':<45} {'Intención':<25} {'Score'}")
print("-" * 80)
for msg in casos:
    intencion = classify(msg)
    print(f"{msg:<45} {str(intencion):<25}")
