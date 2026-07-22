import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.config.oci_model import oci_model
from strands import Agent

print("\nProbando límite de contexto del modelo...\n")

# Texto de relleno (~4 tokens por palabra)
WORD = "navegación "
sizes = [1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000]

for target_tokens in sizes:
    # ~4 chars por token aproximadamente
    chars = target_tokens * 4
    filler = WORD * (chars // len(WORD))

    try:
        agent = Agent(
            model=oci_model,
            system_prompt=f"Eres un asistente. Contexto: {filler}",
            tools=[],
            callback_handler=None,
        )
        response = agent("Responde solo: OK")

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", "?")
        output_tokens = getattr(usage, "output_tokens", "?")
        text = ""
        if hasattr(response, "message") and response.message:
            for block in response.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    text += block.get("text", "")

        status = "✅" if output_tokens and int(output_tokens) > 0 else "❌ FALLO"
        print(f"{status} ~{target_tokens:5d} tokens input → input={input_tokens} output={output_tokens} respuesta='{text[:30]}'")

        if output_tokens and int(output_tokens) == 0:
            print(f"\n⚠️  LÍMITE DETECTADO: el modelo falla con ~{target_tokens} tokens de input")
            break

    except Exception as e:
        print(f"❌ ~{target_tokens:5d} tokens → ERROR: {e}")
        break
