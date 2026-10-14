import asyncio
import os
import re

import edge_tts
import pygame
import speech_recognition as sr
from dotenv import load_dotenv
from langchain.agents import create_agent
from google.genai.errors import ServerError

load_dotenv()

# LangChain's Google provider reads GOOGLE_API_KEY. You may name your key
# GEMINI_API_KEY in .env; this line maps it to the name the provider expects.
if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Customize the personality text and greeting. These are ordinary user-level
# instructions, not hidden system prompts.
PERSONAS = {
    "1": {
        "name": "JARVIS",
        "title": "Just A Rather Very Intelligent System",
        "personality": "calm, polite, witty, and fiercely loyal",
        "voice": "en-GB-RyanNeural",
        "rate": "+0%",
        "greeting": "Welcome back, sir.",
    },
    "2": {
        "name": "FRIDAY",
        "title": "Female Replacement Intelligent Digital Assistant Youth",
        "personality": "direct, pragmatic, expressive, and highly protective",
        "voice": "en-IE-EmilyNeural",
        "rate": "+5%",
        "greeting": "Boss, systems are online and ready for deployment.",
    },
}


def load_mcp_tools():
    """Load Canvas course and assignment tools through MCP."""
    import asyncio
    import json
    import os
    import shutil
    from pathlib import Path

    from dotenv import load_dotenv
    from langchain_core.tools import StructuredTool, ToolException
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Load Canvas credentials from the project's existing .env.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    token = os.getenv("CANVAS_API_TOKEN")
    base_url = os.getenv("CANVAS_BASE_URL") or os.getenv("CANVAS_URL")
    if not token or not base_url:
        raise RuntimeError(
            "Set CANVAS_API_TOKEN and CANVAS_URL in your .env file."
        )

    uvx = shutil.which("uvx")
    if not uvx:
        raise RuntimeError("Install uv first: python -m pip install uv")

    server = StdioServerParameters(
        command=uvx,
        args=[
            "--from", "canvas-lms-mcp==0.1.2",
            "python", "-c",
            "from canvas_lms_mcp.main import mcp; "
            "mcp.run(transport='stdio')",
        ],
        env={
            "CANVAS_API_TOKEN": token,
            "CANVAS_BASE_URL": base_url.rstrip("/"),
        },
    )

    async def request(tool_name=None, arguments=None):
        # Each request owns its session and closes it afterward.
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                if tool_name is None:
                    return (await session.list_tools()).tools

                result = await session.call_tool(
                    tool_name, arguments=arguments or {}
                )
                text = "\n".join(
                    block.text
                    for block in result.content
                    if block.type == "text"
                )
                if result.is_error:
                    raise ToolException(text or "Canvas MCP request failed.")

                if result.structured_content is not None:
                    return json.dumps(result.structured_content)
                return text

    def make_sync_call(tool_name):
        def call(**arguments):
            return asyncio.run(request(tool_name, arguments))
        return call

    # Expose only tools that read courses and assignments.
    allowed = {
        "list_courses",
        "get_course",
        "list_assignments",
        "get_assignment",
    }
    tools = [
        StructuredTool(
            name=tool.name,
            description=tool.description or tool.name,
            args_schema=tool.input_schema,
            func=make_sync_call(tool.name),
            handle_tool_error=True,
        )
        for tool in asyncio.run(request())
        if tool.name in allowed
    ]
    if not tools:
        raise RuntimeError("No matching Canvas MCP tools were discovered.")

    return tools


def play_audio(file_path: str):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.quit()


async def generate_speech(text: str, voice: str, rate: str, output_file: str = "temp_speech.mp3"):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_file)


def speak(text: str, persona: dict) -> None:
    import shutil
    import subprocess
    from contextlib import suppress

    print(f"\n[{persona['name']}]: {text}\n")
    clean_text = re.sub(r"[*_#]", "", text).strip()
    if not clean_text:
        return

    ffplay = shutil.which("ffplay")
    if not ffplay:
        raise RuntimeError("ffplay was not found. Install FFmpeg first.")

    async def stream_audio():
        player = await asyncio.create_subprocess_exec(
            ffplay,
            "-nodisp", "-autoexit",
            "-loglevel", "error",
            "-f", "mp3",
            "-probesize", "1024",
            "-analyzeduration", "0",
            "-i", "pipe:0",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),
        )

        try:
            communicate = edge_tts.Communicate(
                clean_text,
                voice=persona["voice"],
                rate=persona["rate"],
            )

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    player.stdin.write(chunk["data"])
                    await player.stdin.drain()

            # Signal the end of the stream, then finish playback.
            player.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await player.stdin.wait_closed()

            exit_code = await player.wait()
            if exit_code != 0:
                raise RuntimeError(f"ffplay exited with code {exit_code}")
        finally:
            if player.returncode is None:
                player.terminate()
                await player.wait()

    try:
        asyncio.run(stream_audio())
    except edge_tts.exceptions.NoAudioReceived:
        print(
            "[Speech service returned no audio. "
            "The response is displayed above; continuing.]"
        )


def configure_agent(persona: dict):
    from langchain_google_genai import ChatGoogleGenerativeAI

    model = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        thinking_level="minimal",
    )
    return create_agent(model=model, tools=load_mcp_tools())


def listen() -> str:
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.0  # Allow pauses up to 2 seconds
    recognizer.dynamic_energy_threshold = True
    recognizer.operation_timeout = 15

    with sr.Microphone() as source:

        print("\n[Listening...]")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(
                source,
                timeout=10,             # Wait up to 10 seconds for you to begin
                phrase_time_limit=60,  # Record up to 60 seconds of speech
            )
        except sr.WaitTimeoutError:
            return ""

    try:
        text = recognizer.recognize_google(audio)
        print(f"[You]: {text}")
        return text.strip()
    except sr.UnknownValueError:
        return ""
    except (sr.RequestError, OSError) as exc:
        print(f"[Speech recognition connection failed: {exc}]")
        print("Please repeat your request.")
        return ""


def select_persona() -> str:
    print("\n---------------- SELECT PERSONALITY ----------------")
    for key, persona in PERSONAS.items():
        print(f"[{key}] {persona['name']} - {persona['title']}")
    print("-----------------------------------------------------")
    while True:
        choice = input("Choose a personality (1-2): ").strip()
        if choice in PERSONAS:
            return choice
        print("Please choose one of the listed options.")


def main():
    active_key = select_persona()
    persona = PERSONAS[active_key]
    agent = configure_agent(persona)
    speak(persona["greeting"], persona)

    while True:
        try:
            prompt = listen()
            if not prompt:
                continue
            clean_prompt = prompt.lower().strip()
            if clean_prompt in ["exit", "quit", "stop", "goodbye"]:
                speak("Goodbye!", persona)
                break
            if "switch voice" in clean_prompt or "change personality" in clean_prompt:
                active_key = select_persona()
                persona = PERSONAS[active_key]
                agent = configure_agent(persona)
                speak(persona["greeting"], persona)
                continue

            user_request = (
                f"Respond as {persona['name']}. Your personality is {persona['personality']}. "
                "Keep the response clear and natural for speech. "
                f"The user's request is: {prompt}"
            )
            try:
                result = agent.invoke({
                    "messages": [{"role": "user", "content": user_request}]
                })
            except ServerError as exc:
                if exc.code != 503:
                    raise
                speak(
                    "Google's model is busy. Please try your request again shortly.",
                    persona,
                )
                continue
            message = result["messages"][-1]
            output_text = getattr(message, "text", str(message.content)).strip()
            speak(output_text, persona)
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break


if __name__ == "__main__":
    main()