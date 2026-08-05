import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.oci_model import oci_model
from app.state.session import SessionState
from app.prompts.system_prompt import build_system_prompt
from app.tools.telcel_tools import make_tools
from strands import Agent

# Simular sesión de Pedro
session = SessionState()
session.first_name = "Pedro"
session.phone_number = "5555555555"
session.current_plan_name = "Telcel Max Sin Limite 5000"
session.current_cost = 499.0
session.subscription_type = "Abierto"
session.current_plan_gb = 5.0
session.has_promotion = True
session.is_titular = True
session.stage = "PERSUASION"
session.plan_anclado = "Telcel Libre 4 Abierto"

system_prompt = build_system_prompt(session)
tools = make_tools(session)
print(f"\nSystem prompt: {len(system_prompt)} chars")
print(f"Tools: {len(tools)} herramientas")
print(f"\nProbando con historial creciente...\n")

# Mensajes de historial simulados
all_messages = [
    {"role": "assistant", "content": [{"text": "Hola Pedro, le ofrecemos el Telcel Libre 4 Abierto a $499/mes. ¿Le gustaría activarlo?"}]},
    {"role": "user", "content": [{"text": "que beneficios tiene?"}]},
    {"role": "assistant", "content": [{"text": "Lo que gana con el cambio: 10 GB, cashback $74.85/mes, apps ilimitadas. ¿Le gustaría activarlo?"}]},
    {"role": "user", "content": [{"text": "cuanto cuesta el cashback?"}]},
    {"role": "assistant", "content": [{"text": "El cashback es de $74.85/mes y puede usarlo en servicios Telcel. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "tiene claro video?"}]},
    {"role": "assistant", "content": [{"text": "Sí, incluye Claro Video. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "y claro drive?"}]},
    {"role": "assistant", "content": [{"text": "Sí, incluye Claro Drive con 20 GB. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "cuanto tiempo dura la promocion?"}]},
    {"role": "assistant", "content": [{"text": "Esta promoción tiene vigencia el día de hoy. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "puedo decidir despues?"}]},
    {"role": "assistant", "content": [{"text": "Esta promoción tiene vigencia el día de hoy. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "que pasa si se me acaban los datos?"}]},
    {"role": "assistant", "content": [{"text": "Al agotar los GB el servicio se suspende hasta el siguiente ciclo. ¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "ok me interesa"}]},
    {"role": "assistant", "content": [{"text": "¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "si"}]},
    {"role": "assistant", "content": [{"text": "¿Le gustaría activar el Telcel Libre 4 Abierto?"}]},
    {"role": "user", "content": [{"text": "adelante"}]},
]

for n_msgs in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20]:
    history = all_messages[:n_msgs]

    print(f"\n  Historial enviado ({n_msgs} msgs):")
    for i, msg in enumerate(history):
        content = msg['content'][0]['text'][:60] if msg['content'] else ''
        print(f"    [{i}] {msg['role']}: {content}")

    try:
        agent = Agent(
            model=oci_model,
            system_prompt=system_prompt,
            tools=tools,
            callback_handler=None,
            messages=history,
        )
        response = agent("si, adelante")

        text = ""
        if hasattr(response, "message") and response.message:
            for block in response.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    text += block.get("text", "")

        input_tokens = "?"
        output_tokens = "?"
        if hasattr(response, "message") and response.message:
            metadata = response.message.get("metadata", {})
            usage = metadata.get("usage", {})
            input_tokens = usage.get("inputTokens", "?")
            output_tokens = usage.get("outputTokens", "?")

        try:
            out_int = int(output_tokens)
        except (ValueError, TypeError):
            out_int = 1

        status = "✅" if out_int > 0 else "❌ FALLO"
        print(f"{status} history={n_msgs:2d} msgs → input={input_tokens} output={output_tokens} respuesta='{text[:50]}'")

        if out_int == 0:
            print(f"  [DEBUG] message completo: {response.message}")
            print(f"\n⚠️  FALLA con {n_msgs} mensajes de historial")
            break

    except Exception as e:
        print(f"❌ history={n_msgs:2d} msgs → ERROR: {e}")
        break

    # time.sleep(10)  # esperar 10 segundos entre peticiones
