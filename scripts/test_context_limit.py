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
sizes = [1000, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000, 20000, 30000, 40000, 50000]

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

        text = ""
        if hasattr(response, "message") and response.message:
            for block in response.message.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    text += block.get("text", "")

        # Leer tokens del message directamente
        input_tokens = "?"
        output_tokens = "?"
        latency = "?"
        if hasattr(response, "message") and response.message:
            metadata = response.message.get("metadata", {})
            usage = metadata.get("usage", {})
            input_tokens = usage.get("inputTokens", "?")
            output_tokens = usage.get("outputTokens", "?")
            latency = metadata.get("metrics", {}).get("latencyMs", "?")

        try:
            out_int = int(output_tokens)
        except (ValueError, TypeError):
            out_int = 1  # si no podemos leer, asumimos que funcionó

        status = "✅" if out_int > 0 else "❌ FALLO"
        print(f"{status} ~{target_tokens:5d} tokens input → input={input_tokens} output={output_tokens} latency={latency}ms respuesta='{text[:30]}'")

        if out_int == 0:
            print(f"\n⚠️  LÍMITE DETECTADO: el modelo falla con ~{target_tokens} tokens de input")
            break

    except Exception as e:
        print(f"❌ ~{target_tokens:5d} tokens → ERROR: {e}")
        break
