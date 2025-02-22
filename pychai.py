import os
import time
import requests
import json
import re
import threading
import sys

#############################################
# Progress Animation Helpers (Rotating Line)
#############################################

def progress_animation(message, stop_event):
    spinner = ['-', '\\', '|', '/']
    i = 0
    while not stop_event.is_set():
        anim = f"{message} {spinner[i % len(spinner)]}"
        sys.stdout.write("\r" + anim)
        sys.stdout.flush()
        time.sleep(0.15)  # 50% slower than before
        i += 1
    sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
    sys.stdout.flush()

def run_with_progress(message, func, *args, **kwargs):
    stop_event = threading.Event()
    thread = threading.Thread(target=progress_animation, args=(message, stop_event))
    thread.start()
    result = func(*args, **kwargs)
    stop_event.set()
    thread.join()
    return result

#############################################
# Global Configuration and Variables
#############################################

VERSION = "1.4"
# Default conversation model remains the 3b version.
CONVO_MODEL = "hermes-3-llama-3.2-3b"
# Default system model is now set to the 3.1 8b version.
SYS_MODEL = "hermes-3-llama-3.1-8b"
available_models = []

BASE_FOLDER = "memory"
CHARACTERS_FOLDER = os.path.join(BASE_FOLDER, "characters")
SAVED_CONVOS_FOLDER = os.path.join(BASE_FOLDER, "savedconvos")
CONVERSATIONS_FOLDER = os.path.join(BASE_FOLDER, "conversations")
USERNAME_FILE = os.path.join(BASE_FOLDER, "username.txt")
CHARACTERLIST_FILE = os.path.join(BASE_FOLDER, "characterlist.txt")

# conversation_histories stores only the formatted chat messages.
conversation_histories = {}

multi_input_pending = {}   # channel -> dict
confirmation_pending = {}  # channel -> dict

username = ""

role_colors = {
    "system": "\033[33m",  # yellow
    "user": "\033[32m",    # green
    "assistant": "\033[34m",  # blue
    "command": "\033[2m\033[37m"  # dim white
}

valid_colors = {
    "red": "\033[31m",
    "green": "\033[32m",
    "blue": "\033[34m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "magenta": "\033[35m",
    "white": "\033[37m",
    "lightred": "\033[91m",
    "lightgreen": "\033[92m",
    "lightblue": "\033[94m",
    "lightyellow": "\033[93m",
    "lightcyan": "\033[96m",
    "lightmagenta": "\033[95m",
    "lightwhite": "\033[97m",
    "purple": "\033[35m",
    "pink": "\033[95m",
    "babyblue": "\033[94m",
    "babypink": "\033[38;5;218m"
}

CUSTOM_SET_PROMPT = ("Generate a detailed, consistent, high-quality system prompt for this AI character "
                       "that is roleplay-ready. Use the following details exactly and output only the final prompt with no extra commentary.")
CUSTOM_QUESTIONSET_PROMPT = ("Generate a detailed, consistent, high-quality system prompt for this AI character based on the following details. "
                              "The final prompt should be roleplay-ready and formatted consistently. Do not add extra commentary.")

server_status = None

#############################################
# Helper Functions for Output
#############################################

def conversation_output(channel, role, message):
    # Prints a conversation line with proper color formatting.
    if role == "user":
        print(f"{role_colors['user']}{username}\033[0m: {message}")
    elif role == "assistant":
        char_name = channel.lstrip("#")
        if channel == "#welcome":
            char_name = "Velvet's (py)chai"
        print(f"{role_colors['assistant']}{char_name}\033[0m: {message}")
    else:
        print(f"{role_colors['system']}{message}\033[0m")

def command_output(channel, message):
    print(f"{role_colors['command']}{message}\033[0m")

#############################################
# LM Studio API Endpoint Helpers
#############################################

def get_lm_api_url():
    try:
        r = requests.get("http://localhost:1234/v1/models", timeout=2)
        if r.status_code == 200:
            return "http://localhost:1234/v1/chat/completions"
    except Exception:
        pass
    return "http://velvet.tinysun.net:1234/v1/chat/completions"

def get_models_url():
    try:
        r = requests.get("http://localhost:1234/v1/models", timeout=2)
        if r.status_code == 200:
            return "http://localhost:1234/v1/models"
    except Exception:
        pass
    return "http://velvet.tinysun.net:1234/v1/models"

def test_connection():
    try:
        start = time.time()
        r = requests.get("http://localhost:1234/v1/models", timeout=2)
        ping = (time.time() - start) * 1000
        if r.status_code == 200:
            return f"Connected to LM Studio at localhost (ping: {int(ping)}ms)"
    except Exception:
        pass
    try:
        start = time.time()
        r = requests.get("http://velvet.tinysun.net:1234/v1/models", timeout=2)
        ping = (time.time() - start) * 1000
        if r.status_code == 200:
            return f"Connected to LM Studio at velvet.tinysun.net (ping: {int(ping)}ms)"
    except Exception:
        pass
    return "Not connected to any LM Studio API."

#############################################
# Conversation History Management
#############################################

def process_reply(reply):
    pattern = r'^\(.*?\)\s*\[(.*)\]$'
    match = re.match(pattern, reply)
    if match:
        return match.group(1).strip()
    return reply.rstrip()

def load_conversation_history(channel):
    global conversation_histories
    if channel not in conversation_histories:
        conversation_histories[channel] = []
        if channel == "#welcome":
            default_prompt = (
                "[WELCOME SYSTEM PROMPT]\n"
                "Welcome to Velvet's (py)chai version " + VERSION + "!\n"
                "This tool lets you roleplay with AI characters. Commands:\n"
                "  !create <name>         - Create a new character\n"
                "  !character <name>      - Switch characters (auto-saves current conversation)\n"
                "  !duplicate <name>      - Duplicate current character to a new one\n"
                "  !set                   - Update the system prompt\n"
                "  !improve/sharpen/fixate - Improve the system prompt based on your advice\n"
                "  !selfimprove [score]   - Automatically improve the system prompt until graded above a threshold (default 80)\n"
                "  !connection            - Test connection to LM Studio API\n"
                "  !characterlist         - List characters with one-sentence summaries (pass 'remake' to regenerate)\n"
                "  !setcolor <role> <color> - Customize colors (roles: system, user, assistant, command)\n"
                "  !convomodel            - Switch conversation model\n"
                "  !sysmodel              - Switch system model\n"
                "  !exit                  - Save conversation and exit\n"
                "Simply type your messages to chat.\n"
                "Enjoy!"
            )
            conversation_histories[channel].append({"role": "system", "content": default_prompt})
        else:
            char_name = channel.lstrip("#")
            filename = os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt")
            if os.path.exists(filename):
                try:
                    with open(filename, "r", encoding="utf-8") as f:
                        prompt = f.read().strip()
                    if prompt:
                        conversation_histories[channel].append({"role": "system", "content": prompt})
                except Exception as e:
                    command_output(channel, f"Error loading system prompt from {filename}: {e}")
            else:
                default_prompt = (
                    "[SYSTEM PROMPT]\n"
                    "Background: You are an engaging conversational AI.\n"
                    "Personality: Friendly, concise, and interactive.\n"
                    "Guidelines:\n"
                    "- Keep responses brief (1-3 sentences)\n"
                    "- Always leave room for the user to respond\n"
                    "- Stay in character at all times"
                )
                conversation_histories[channel].append({"role": "system", "content": default_prompt})

def save_conversation(channel):
    if channel in conversation_histories:
        # Build formatted log using color codes.
        log_lines = []
        for msg in conversation_histories[channel]:
            if msg["role"] == "user":
                log_lines.append(f"{role_colors['user']}{username}\033[0m: {msg['content']}")
            elif msg["role"] == "assistant":
                char_name = channel.lstrip("#")
                if channel == "#welcome":
                    char_name = "Velvet's (py)chai"
                log_lines.append(f"{role_colors['assistant']}{char_name}\033[0m: {msg['content']}")
            else:
                log_lines.append(f"{role_colors['system']}{msg['content']}\033[0m")
        log = "\n".join(log_lines)
        filename = os.path.join(SAVED_CONVOS_FOLDER, f"{channel.lstrip('#')}_saved.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(log)
            command_output(channel, f"Conversation saved as {filename}.")
        except Exception as e:
            command_output(channel, f"Error saving conversation: {e}")

def clear_conversation(channel):
    global conversation_histories
    if channel in conversation_histories and conversation_histories[channel]:
        if conversation_histories[channel][0]["role"] == "system":
            conversation_histories[channel] = [conversation_histories[channel][0]]
        else:
            conversation_histories[channel] = []
    else:
        conversation_histories[channel] = []

def reload_conversation(channel):
    global conversation_histories
    char_name = channel.lstrip("#")
    filename = os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt")
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                prompt = f.read().strip()
            if prompt:
                conversation_histories[channel] = [{"role": "system", "content": prompt}]
                return True
        except Exception as e:
            command_output(channel, f"Error reloading system prompt from {filename}: {e}")
    return False

#############################################
# LM Studio API Integration (with Stream Support)
#############################################

def process_api_request(channel, payload, sock_file):
    try:
        payload["stream"] = False
        api_url = get_lm_api_url()
        response = requests.post(api_url, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            data = response.json()
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if reply:
                reply = process_reply(reply)
                conversation_histories[channel].append({"role": "assistant", "content": reply})
                conversation_output(channel, "assistant", reply)
            else:
                command_output(channel, "AI returned an empty reply.")
        else:
            command_output(channel, f"API Error: {response.status_code}")
    except Exception as e:
        command_output(channel, f"Error contacting LM Studio API: {e}")

def process_api_request_stream(channel, payload, sock_file):
    try:
        payload["stream"] = True
        api_url = get_lm_api_url()
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        data = json.dumps(payload)
        # Print assistant header once before streaming.
        sys.stdout.write(f"{role_colors['assistant']}{channel.lstrip('#')}\033[0m: ")
        sys.stdout.flush()
        response = requests.post(api_url, data=data, headers=headers, stream=True)
        if response.status_code != 200:
            command_output(channel, f"API Error: {response.status_code}")
            return
        collected = ""
        for chunk in response.iter_lines(decode_unicode=True):
            if chunk:
                if chunk.startswith("data:"):
                    chunk = chunk[len("data:"):].strip()
                try:
                    json_data = json.loads(chunk)
                    token = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if token:
                        collected += token
                        sys.stdout.write(token)
                        sys.stdout.flush()
                except json.JSONDecodeError:
                    continue
        sys.stdout.write("\n")
        sys.stdout.flush()
        # Append full reply without reprinting.
        conversation_histories[channel].append({"role": "assistant", "content": collected})
    except Exception as e:
        command_output(channel, f"Error contacting LM Studio API: {e}")

#############################################
# Confirmation and Improvement Response Processing
#############################################

def prompt_confirmation(sock_file, channel, summary):
    command_output(channel, "Improvement pending. Options: 1) confirm  2) get  3) retry  4) cancel")
    command_output(channel, f"Change Summary: {summary}")

def process_confirmation_response(channel, sender, response, sock_file):
    pending = confirmation_pending.get(channel)
    if not pending:
        return False
    if pending.get("type") == "improvement":
        resp = response.lower()
        if resp in ["1", "confirm"]:
            conversation_histories[channel][0]["content"] = pending["new_prompt"]
            command_output(channel, "New system prompt accepted and saved.")
            if pending["command"] in ["sharpen", "fixate"]:
                for i in range(len(conversation_histories[channel]) - 1, -1, -1):
                    if conversation_histories[channel][i]["role"] == "assistant":
                        conversation_histories[channel].pop(i)
                        command_output(channel, "Regenerating previous assistant message...")
                        payload = {"model": SYS_MODEL, "messages": conversation_histories[channel]}
                        process_api_request(channel, payload, sock_file)
                        break
            if pending["command"] == "fixate":
                conversation_histories[channel].append({"role": "system", "content": f"Hint: {pending['feedback']}"})
            char_name = channel.lstrip("#")
            filename = os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt")
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(pending["new_prompt"])
                command_output(channel, "New system prompt saved permanently.")
            except Exception as e:
                command_output(channel, f"Error saving system prompt: {e}")
            confirmation_pending.pop(channel, None)
        elif resp in ["2", "get"]:
            command_output(channel, f"New system prompt:\n{pending['new_prompt']}")
        elif resp in ["3", "retry"]:
            command_output(channel, "Generating improved backstory...")
            old_prompt = pending["old_prompt"]
            feedback = pending["feedback"]
            instruction = (
                "Improve the following system prompt by adding more descriptive details and enhancements without removing any original information. "
                "Ensure the final output is a refined system prompt suitable for guiding an AI character's behavior. "
                "Do not include any greetings or extraneous text; output only the final improved system prompt.\n"
                "Original system prompt:\n" + old_prompt
            )
            payload = {"model": SYS_MODEL, "messages": [{"role": "user", "content": instruction}]}
            try:
                response_retry = run_with_progress("Generating improved backstory", lambda: requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"}))
                if response_retry.status_code != 200:
                    command_output(channel, f"LM Studio API error during prompt improvement: {response_retry.status_code}")
                    return True
                data_retry = response_retry.json()
                new_prompt = data_retry.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not new_prompt:
                    command_output(channel, "LM Studio API returned an empty new system prompt.")
                    return True
                new_prompt = process_reply(new_prompt)
            except Exception as e:
                command_output(channel, f"Error during prompt improvement: {e}")
                return True
            summary_instruction = (
                "Below is the current system prompt:\n" + old_prompt +
                "\n\nBelow is the new improved system prompt:\n" + new_prompt +
                "\n\nProvide a one-line summary of the changes (mention what was improved):"
            )
            payload_summary = {"model": SYS_MODEL, "messages": [{"role": "user", "content": summary_instruction}]}
            try:
                response_summary = run_with_progress("Generating Difference Summary", lambda: requests.post(get_lm_api_url(), json=payload_summary, headers={"Content-Type": "application/json"}))
                if response_summary.status_code == 200:
                    data_summary = response_summary.json()
                    summary = process_reply(data_summary.get("choices", [{}])[0].get("message", {}).get("content", ""))
                else:
                    summary = f"LM Studio API error during summary generation: {response_summary.status_code}"
            except Exception as e:
                summary = f"Error during summary generation: {e}"
            confirmation_pending[channel]["new_prompt"] = new_prompt
            prompt_confirmation(sock_file, channel, summary)
        elif resp in ["4", "cancel"]:
            confirmation_pending.pop(channel, None)
            command_output(channel, "Improvement canceled.")
        return True
    else:
        if response in ["yes", "no"]:
            if response == "yes":
                if pending["command"] == "clearbackstory":
                    if channel in conversation_histories and conversation_histories[channel]:
                        if conversation_histories[channel][0]["role"] == "system":
                            conversation_histories[channel] = [conversation_histories[channel][0]]
                        else:
                            conversation_histories[channel] = []
                        command_output(channel, "Backstory cleared.")
                    else:
                        command_output(channel, "No backstory to clear.")
                elif pending["command"] == "delete":
                    if channel.lower() == "#welcome":
                        command_output(channel, "Cannot delete the default character.")
                    else:
                        char_name = channel.lstrip("#")
                        filename = os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt")
                        if os.path.exists(filename):
                            try:
                                os.remove(filename)
                                if channel in conversation_histories:
                                    del conversation_histories[channel]
                                command_output(channel, f"Character '{char_name}' and its file have been deleted.")
                            except Exception as e:
                                command_output(channel, f"Error deleting character '{char_name}': {e}")
                        else:
                            command_output(channel, f"No file exists for character '{char_name}'.")
                confirmation_pending.pop(channel, None)
            elif response == "no":
                command_output(channel, f"{pending['command']} command canceled.")
                confirmation_pending.pop(channel, None)
            return True
    return False

#############################################
# Self-Improve Command (Beta Feature)
#############################################

def process_selfimprove(channel, sender, argument, sock_file):
    try:
        threshold = int(argument.strip()) if argument.strip().isdigit() else 80
    except:
        threshold = 80
    if channel not in conversation_histories or not conversation_histories[channel] or conversation_histories[channel][0]["role"] != "system":
        command_output(channel, "No system prompt to improve.")
        return True
    old_prompt = conversation_histories[channel][0]["content"]
    improved_prompt = None
    grade = 0
    while True:
        instruction = (
            "Improve the following system prompt by adding more descriptive details and enhancements without removing any original information. "
            "Ensure the final output is a refined system prompt suitable for guiding an AI character's behavior. "
            "Do not include any greetings or extraneous text; output only the final improved system prompt.\n"
            "Original system prompt:\n" + old_prompt
        )
        payload = {"model": SYS_MODEL, "messages": [{"role": "user", "content": instruction}]}
        try:
            response = run_with_progress("Generating improved backstory", lambda: requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"}))
            if response.status_code != 200:
                command_output(channel, f"LM Studio API error during selfimprove: {response.status_code}")
                return True
            data = response.json()
            improved_prompt = process_reply(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
        except Exception as e:
            command_output(channel, f"Error during selfimprove: {e}")
            return True
        grade_instruction = (
            "On a scale from 0 to 100, grade the following system prompt solely based on user experience and clarity. "
            "Return only the number.\n" + improved_prompt
        )
        payload_grade = {"model": SYS_MODEL, "messages": [{"role": "user", "content": grade_instruction}]}
        try:
            response_grade = run_with_progress("Generating backstory grade", lambda: requests.post(get_lm_api_url(), json=payload_grade, headers={"Content-Type": "application/json"}))
            if response_grade.status_code != 200:
                command_output(channel, f"LM Studio API error during grading: {response_grade.status_code}")
                return True
            data_grade = response_grade.json()
            grade_str = process_reply(data_grade.get("choices", [{}])[0].get("message", {}).get("content", ""))
            try:
                grade = int(''.join(filter(str.isdigit, grade_str)))
            except:
                grade = 0
        except Exception as e:
            command_output(channel, f"Error during grading: {e}")
            return True
        command_output(channel, f"Self-improve iteration: grade = {grade}")
        if grade >= threshold:
            break
        else:
            old_prompt = improved_prompt
    summary_instruction = (
        "Below is the current system prompt:\n" + conversation_histories[channel][0]["content"] +
        "\n\nBelow is the new improved system prompt:\n" + improved_prompt +
        "\n\nProvide a one-line summary of the changes (mention what was improved):"
    )
    payload_summary = {"model": SYS_MODEL, "messages": [{"role": "user", "content": summary_instruction}]}
    try:
        response_summary = run_with_progress("Generating Difference Summary", lambda: requests.post(get_lm_api_url(), json=payload_summary, headers={"Content-Type": "application/json"}))
        if response_summary.status_code == 200:
            data_summary = response_summary.json()
            summary = process_reply(data_summary.get("choices", [{}])[0].get("message", {}).get("content", ""))
        else:
            summary = "No summary provided."
    except Exception as e:
        summary = f"Error during summary generation: {e}"
    confirmation_pending[channel] = {
        "type": "improvement",
        "command": "selfimprove",
        "old_prompt": conversation_histories[channel][0]["content"],
        "feedback": f"Self-improve iteration completed with grade {grade}",
        "new_prompt": improved_prompt
    }
    prompt_confirmation(sock_file, channel, summary)
    return True

#############################################
# Command Processing Functions
#############################################

def process_commands_section1(channel, sender, command, argument, sock_file, active_users):
    global current_channel
    if command == "create":
        if argument:
            new_character = argument.strip()
            new_channel = "#" + new_character
            filename = os.path.join(CHARACTERS_FOLDER, f"{new_character}.txt")
            if not os.path.exists(filename):
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("")
                command_output(channel, f"File '{filename}' created.")
            else:
                command_output(channel, f"File '{filename}' already exists.")
            load_conversation_history(new_channel)
            command_output(new_channel, f"Character '{new_character}' created.")
            current_channel = new_channel
            command_output(current_channel, f"Switched to character '{new_character}'.")
        else:
            command_output(channel, "Usage: !create <character_name>")
        return True
    elif command == "duplicate":
        if argument:
            new_character = argument.strip()
            source_character = current_channel.lstrip("#")
            if source_character.lower() == "welcome":
                command_output(channel, "Default character cannot be duplicated.")
                return True
            source_file = os.path.join(CHARACTERS_FOLDER, f"{source_character}.txt")
            if not os.path.exists(source_file):
                command_output(channel, f"Warning: Source character file for '{source_character}' does not exist. Cannot duplicate.")
                return True
            new_file = os.path.join(CHARACTERS_FOLDER, f"{new_character}.txt")
            if os.path.exists(new_file):
                command_output(channel, f"Character '{new_character}' already exists.")
                return True
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(new_file, "w", encoding="utf-8") as f:
                    f.write(content)
                command_output(channel, f"Character duplicated as '{new_character}'.")
                save_conversation(channel)
                current_channel = "#" + new_character
                load_conversation_history(current_channel)
                command_output(current_channel, f"Switched to character '{new_character}'.")
            except Exception as e:
                command_output(channel, f"Error duplicating character: {e}")
        else:
            command_output(channel, "Usage: !duplicate <new_character_name>")
        return True
    elif command == "clear":
        clear_conversation(channel)
        command_output(channel, "Memory cleared.")
        return True
    elif command == "clearbackstory":
        confirmation_pending[channel] = {"command": "clearbackstory", "sender": sender}
        command_output(channel, "Are you sure you want to clear the backstory? (yes/no)")
        return True
    elif command == "reload":
        if reload_conversation(channel):
            command_output(channel, "System prompt reloaded.")
        else:
            command_output(channel, "Failed to reload system prompt.")
        return True
    elif command == "get":
        if channel in conversation_histories and conversation_histories[channel]:
            sys_prompt = conversation_histories[channel][0]["content"] if conversation_histories[channel][0]["role"] == "system" else ""
            if sys_prompt:
                command_output(channel, f"Backstory:\n{sys_prompt}")
            else:
                command_output(channel, "No backstory set.")
        else:
            command_output(channel, "No backstory set.")
        return True
    elif command == "exit":
        save_conversation(channel)
        command_output(channel, "Exiting. Conversation saved.")
        exit(0)
    return False

def process_commands_section3(channel, sender, command, argument, sock_file):
    if channel in multi_input_pending:
        return True
    if channel in confirmation_pending and confirmation_pending[channel].get("type") == "improvement":
        return True
    if command == "selfimprove":
        return process_selfimprove(channel, sender, argument, sock_file)
    if command not in ["improve", "sharpen", "fixate"]:
        return False
    if not argument.strip():
        command_output(channel, f"Usage: !{command} <improvement advice>")
        return True
    if channel in conversation_histories and conversation_histories[channel] and conversation_histories[channel][0]["role"] == "system":
        old_prompt = conversation_histories[channel][0]["content"]
    else:
        command_output(channel, "No existing system prompt found.")
        return True
    feedback = argument.strip()
    instruction = (
        "Below is the current system prompt:\n" + old_prompt +
        "\n\nImprove the system prompt using the following advice:\n" + feedback +
        "\n\nCombine the old prompt and the improvement advice to generate a new system prompt that incorporates the changes while retaining all original details. "
        "Return only the final system prompt with no additional commentary."
    )
    payload = {"model": SYS_MODEL, "messages": [{"role": "user", "content": instruction}]}
    try:
        response = run_with_progress("Generating improved backstory", lambda: requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"}))
        if response.status_code != 200:
            command_output(channel, f"LM Studio API error during prompt improvement: {response.status_code}")
            return True
        data = response.json()
        new_prompt = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not new_prompt:
            command_output(channel, "LM Studio API returned an empty new system prompt.")
            return True
        new_prompt = process_reply(new_prompt)
        summary_instruction = (
            "Below is the current system prompt:\n" + old_prompt +
            "\n\nBelow is the new improved system prompt:\n" + new_prompt +
            "\n\nProvide a one-line summary of the changes (mention what was improved):"
        )
        payload_summary = {"model": SYS_MODEL, "messages": [{"role": "user", "content": summary_instruction}]}
        try:
            response_summary = run_with_progress("Generating Difference Summary", lambda: requests.post(get_lm_api_url(), json=payload_summary, headers={"Content-Type": "application/json"}))
            if response_summary.status_code == 200:
                data_summary = response_summary.json()
                summary = data_summary.get("choices", [{}])[0].get("message", {}).get("content", "")
                if summary:
                    summary = process_reply(summary)
                else:
                    summary = "No summary provided by AI."
            else:
                summary = f"LM Studio API error during summary generation: {response_summary.status_code}"
        except Exception as e:
            summary = f"Error during summary generation: {e}"
        confirmation_pending[channel] = {
            "type": "improvement",
            "command": command,
            "old_prompt": old_prompt,
            "feedback": feedback,
            "new_prompt": new_prompt
        }
        prompt_confirmation(sock_file, channel, summary)
    except Exception as e:
        command_output(channel, f"Error during prompt improvement: {e}")
    return True

def process_commands_section4(channel, sender, command, argument, sock_file, active_users):
    global SYS_MODEL, CONVO_MODEL, available_models
    if command == "serve":
        payload = {"model": CONVO_MODEL, "messages": conversation_histories.get(channel, []), "stream": True}
        process_api_request_stream(channel, payload, sock_file)
        return True
    elif command == "convomodel":
        if not available_models:
            try:
                response = requests.get(get_models_url(), timeout=2)
                data = response.json()
                available_models.extend([m["id"] for m in data["data"]])
            except Exception as e:
                command_output(channel, f"Error fetching models: {e}")
                return True
        command_output(channel, "Available conversation models:")
        for idx, model in enumerate(available_models, start=1):
            command_output(channel, f"{idx}. {model}")
        if argument:
            try:
                model_index = int(argument.strip())
                if 1 <= model_index <= len(available_models):
                    CONVO_MODEL = available_models[model_index - 1]
                    command_output(channel, f"Conversation model switched to {CONVO_MODEL}")
                else:
                    command_output(channel, "Invalid model number.")
            except ValueError:
                command_output(channel, "Usage: !convomodel <number>")
        return True
    elif command == "sysmodel":
        if not available_models:
            try:
                response = requests.get(get_models_url(), timeout=2)
                data = response.json()
                available_models.extend([m["id"] for m in data["data"]])
            except Exception as e:
                command_output(channel, f"Error fetching models: {e}")
                return True
        command_output(channel, "Available system models:")
        for idx, model in enumerate(available_models, start=1):
            command_output(channel, f"{idx}. {model}")
        if argument:
            try:
                model_index = int(argument.strip())
                if 1 <= model_index <= len(available_models):
                    SYS_MODEL = available_models[model_index - 1]
                    command_output(channel, f"System model switched to {SYS_MODEL}")
                else:
                    command_output(channel, "Invalid model number.")
            except ValueError:
                command_output(channel, "Usage: !sysmodel <number>")
        return True
    elif command == "hint":
        if not argument:
            command_output(channel, "Usage: !hint <instruction>")
            return True
        if conversation_histories[channel] and conversation_histories[channel][0]["role"] == "system":
            if len(conversation_histories[channel]) > 1 and conversation_histories[channel][1]["role"] == "system" and conversation_histories[channel][1]["content"].startswith("Hint:"):
                conversation_histories[channel][1]["content"] = f"Hint: {argument}"
            else:
                conversation_histories[channel].insert(1, {"role": "system", "content": f"Hint: {argument}"})
        else:
            conversation_histories[channel].insert(0, {"role": "system", "content": f"Hint: {argument}"})
        if conversation_histories[channel] and conversation_histories[channel][-1]["role"] in ["assistant", "user"]:
            conversation_histories[channel].pop()
            command_output(channel, "Previous response removed due to hint. Regenerating...")
            user_msg = conversation_histories[channel][-1]["content"]
            conversation_histories[channel].append({"role": "user", "content": user_msg})
            payload = {"model": CONVO_MODEL, "messages": conversation_histories[channel], "stream": True}
            process_api_request_stream(channel, payload, sock_file)
        return True
    elif command == "user":
        last_assistant = None
        for msg in reversed(conversation_histories.get(channel, [])):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break
        if not last_assistant:
            command_output(channel, "No assistant message found to respond to.")
            return True
        user_prompt = f"Generate a user reply to the following assistant message:\n{last_assistant}"
        payload = {"model": CONVO_MODEL, "messages": [{"role": "user", "content": user_prompt}]}
        run_with_progress("Generating user reply", lambda: requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"}))
        try:
            response = requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"})
            if response.status_code == 200:
                data = response.json()
                user_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if user_reply:
                    user_reply = process_reply(user_reply)
                    conversation_histories[channel].append({"role": "user", "content": user_reply})
                    conversation_output(channel, "user", user_reply)
                else:
                    command_output(channel, "LM Studio API returned an empty user reply.")
            else:
                command_output(channel, f"LM Studio API error during user command: {response.status_code}")
        except Exception as e:
            command_output(channel, f"Error contacting LM Studio API during user command: {e}")
        return True
    elif command == "edit":
        if not argument:
            command_output(channel, "Usage: !edit <new user message>")
            return True
        found = False
        for i in range(len(conversation_histories[channel]) - 1, -1, -1):
            if conversation_histories[channel][i]["role"] == "user":
                conversation_histories[channel][i]["content"] = argument
                found = True
                break
        if not found:
            command_output(channel, "No user message found to edit.")
            return True
        for i in range(len(conversation_histories[channel]) - 1, -1, -1):
            if conversation_histories[channel][i]["role"] == "assistant":
                conversation_histories[channel].pop(i)
                break
        command_output(channel, "User message edited. Regenerating assistant response...")
        payload = {"model": CONVO_MODEL, "messages": conversation_histories[channel], "stream": True}
        process_api_request_stream(channel, payload, sock_file)
        return True
    elif command == "assistantedit":
        if not argument:
            command_output(channel, "Usage: !assistantedit <new assistant message>")
            return True
        found = False
        for i in range(len(conversation_histories[channel]) - 1, -1, -1):
            if conversation_histories[channel][i]["role"] == "assistant":
                conversation_histories[channel][i]["content"] = argument
                found = True
                break
        if not found:
            command_output(channel, "No assistant message found to edit.")
        else:
            command_output(channel, "Assistant message edited.")
        return True
    elif command == "log":
        if channel in conversation_histories:
            for msg in conversation_histories[channel]:
                if msg["role"] == "user":
                    print(f"{role_colors['user']}{username}\033[0m: {msg['content']}")
                elif msg["role"] == "assistant":
                    char_name = channel.lstrip("#")
                    if channel == "#welcome":
                        char_name = "Velvet's (py)chai"
                    print(f"{role_colors['assistant']}{char_name}\033[0m: {msg['content']}")
                else:
                    print(f"{role_colors['system']}{msg['content']}\033[0m")
        else:
            command_output(channel, "No conversation history available.")
        return True
    elif command == "save":
        save_conversation(channel)
        return True
    elif command == "load":
        filename = os.path.join(SAVED_CONVOS_FOLDER, f"{channel.lstrip('#')}_saved.txt")
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                loaded_history = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if ": " in line:
                        role, content = line.split(": ", 1)
                        if role.lower() == "system":
                            continue
                        loaded_history.append({"role": role, "content": content})
                if channel in conversation_histories and conversation_histories[channel]:
                    system_msg = conversation_histories[channel][0]
                else:
                    load_conversation_history(channel)
                    system_msg = conversation_histories[channel][0]
                conversation_histories[channel] = [system_msg] + loaded_history
                command_output(channel, "Conversation history loaded from saved file.")
            except Exception as e:
                command_output(channel, f"Error loading saved conversation: {e}")
        else:
            command_output(channel, "No saved conversation found.")
        return True
    elif command == "delete":
        if channel.lower() == "#welcome":
            command_output(channel, "Cannot delete the default character.")
            return True
        confirmation_pending[channel] = {"command": "delete", "sender": sender}
        command_output(channel, "Are you sure you want to delete this character? (yes/no)")
        return True
    elif command == "iterate":
        if channel in conversation_histories and len(conversation_histories[channel]) > 0:
            last_msg = conversation_histories[channel][-1]
            if last_msg["role"] in ["assistant", "user"]:
                conversation_histories[channel].pop()
                command_output(channel, "Previous response removed. Regenerating...")
                user_msg = conversation_histories[channel][-1]["content"]
                conversation_histories[channel].append({"role": "user", "content": user_msg})
                payload = {"model": CONVO_MODEL, "messages": conversation_histories[channel], "stream": True}
                process_api_request_stream(channel, payload, sock_file)
        return True
    elif command in ["rawset", "setraw"]:
        if argument:
            new_prompt = argument.strip()
            if channel in conversation_histories and conversation_histories[channel]:
                if conversation_histories[channel][0]["role"] == "system":
                    conversation_histories[channel][0]["content"] = new_prompt
                else:
                    conversation_histories[channel].insert(0, {"role": "system", "content": new_prompt})
            else:
                conversation_histories[channel] = [{"role": "system", "content": new_prompt}]
            char_name = channel.lstrip("#")
            filename = os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt")
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(new_prompt)
                command_output(channel, "System prompt set manually via rawset.")
            except Exception as e:
                command_output(channel, f"Error writing system prompt: {e}")
        else:
            multi_input_pending[channel] = {"command": "setraw", "buffer": "", "is_command": True}
            command_output(channel, "Enter system prompt text. Type 'continue' when done or 'cancel' to abort.")
        return True
    elif command == "set":
        if argument:
            multi_input_pending[channel] = {"command": "set", "buffer": argument.strip(), "is_command": True}
            command_output(channel, "Enter additional lines if needed. Type 'continue' when done or 'cancel' to abort.\nCurrent input: " + multi_input_pending[channel]["buffer"])
        else:
            multi_input_pending[channel] = {"command": "set", "buffer": "", "is_command": True}
            command_output(channel, "Enter system prompt details. Type 'continue' when done or 'cancel' to abort.")
        return True
    elif command == "questionset":
        questions = [
            "Enter the character name:",
            "Enter a detailed background:",
            "Enter personality traits:",
            "Enter special abilities or additional details:",
            "Enter any extra instructions for roleplay:"
        ]
        multi_input_pending[channel] = {
            "command": "questionset",
            "questions": questions,
            "answers": [],
            "question_index": 0,
            "buffer": "",
            "is_command": True,
            "single_line_first": True
        }
        command_output(channel, questions[0] + " (type your answer and press Enter; single line input)")
        return True
    elif command == "connection":
        result = test_connection()
        command_output(channel, result)
        return True
    elif command == "setcolor":
        parts = argument.strip().split()
        if len(parts) != 2:
            command_output(channel, "Usage: !setcolor <role> <color>\nValid roles: system, user, assistant, command.\nValid colors: " + ", ".join(valid_colors.keys()))
            return True
        role, color = parts[0].lower(), parts[1].lower()
        if role not in role_colors:
            command_output(channel, f"Invalid role '{role}'. Valid roles: system, user, assistant, command.")
            return True
        if color not in valid_colors:
            command_output(channel, f"Invalid color '{color}'. Valid colors: " + ", ".join(valid_colors.keys()))
            return True
        role_colors[role] = valid_colors[color]
        command_output(channel, f"Color for {role} messages set to {color}.")
        return True
    elif command == "characterlist":
        # New: if argument "remake" is provided, regenerate the character list.
        remake = argument.strip().lower() == "remake"
        try:
            if not remake and os.path.exists(CHARACTERLIST_FILE):
                with open(CHARACTERLIST_FILE, "r", encoding="utf-8") as f:
                    final_list = f.read().strip()
                command_output(channel, "Character list (loaded from memory):\n" + final_list)
                return True
            char_folder = CHARACTERS_FOLDER
            files = [f for f in os.listdir(char_folder) if f.endswith(".txt")]
            if not files:
                command_output(channel, "No characters found.")
                return True
            command_output(channel, "AI is busy, please wait... generating character summaries")
            summary_lines = []
            for filename in files:
                character = os.path.splitext(filename)[0]
                with open(os.path.join(char_folder, filename), "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    summary = "No system prompt available."
                else:
                    prompt_text = "Provide a one sentence summary of the following character description:\n" + content
                    payload = {"model": SYS_MODEL, "messages": [{"role": "user", "content": prompt_text}]}
                    try:
                        command_output(channel, "Generating character summary...")
                        response = requests.post(get_lm_api_url(), json=payload, headers={"Content-Type": "application/json"})
                        if response.status_code == 200:
                            data = response.json()
                            summary = process_reply(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                        else:
                            summary = "API error " + str(response.status_code)
                    except Exception as e:
                        summary = f"Error: {e}"
                summary_lines.append(f"{character}: {summary}")
            final_list = "\n\n".join(summary_lines)
            with open(CHARACTERLIST_FILE, "w", encoding="utf-8") as f:
                f.write(final_list)
            command_output(channel, "Character list:\n" + final_list)
        except Exception as e:
            command_output(channel, f"Error generating character list: {e}")
        return True
    elif command == "character":
        save_conversation(channel)
        if argument.strip():
            new_channel = "#" + argument.strip()
            current_character_file = os.path.join(CHARACTERS_FOLDER, f"{argument.strip()}.txt")
            current_channel = new_channel
            load_conversation_history(current_channel)
            if not os.path.exists(current_character_file):
                command_output(current_channel, f"Warning: Character file for '{argument.strip()}' does not exist. Using default prompt.")
            command_output(current_channel, f"Switched to character '{argument.strip()}'.")
        else:
            command_output(channel, "Usage: !character {name}")
        return True
    elif command == "help":
        help_msg = (
            "Available commands:\n"
            "create - Create a new character file and switch to it.\n"
            "duplicate - Duplicate current character to a new one and switch to it.\n"
            "delete - Delete the current character (requires confirmation).\n"
            "clear - Clear conversation history (preserving system prompt).\n"
            "clearbackstory - Clear the backstory (requires confirmation).\n"
            "reload - Reload system prompt from file.\n"
            "get - Get the current system prompt/backstory.\n"
            "set - Update system prompt using LM Studio (multiline input; complete with 'continue').\n"
            "rawset - Manually set the system prompt (multiline input supported).\n"
            "questionset - Guided setup for a new character's system prompt (first question is single line).\n"
            "improve/sharpen/fixate - Improve the system prompt; 'sharpen' regenerates the previous assistant message, 'fixate' adds a hint.\n"
            "selfimprove [score] - Automatically improve the system prompt until graded above the threshold (default 80).\n"
            "edit - Replace the previous user message and regenerate a response.\n"
            "assistantedit - Replace the previous assistant message with a custom one.\n"
            "serve - Generate an AI response using the full conversation history with stream support.\n"
            "hint - Add a hint to influence the next AI response and remake the previous answer.\n"
            "convomodel - List available conversation models or switch conversation model by number.\n"
            "sysmodel - List available system models or switch system model by number.\n"
            "user - Generate a user reply to the last assistant message.\n"
            "log - Display the full conversation history with proper formatting.\n"
            "save - Save the current conversation log to a file.\n"
            "load - Load the saved conversation log.\n"
            "iterate - Remove the last response and regenerate it.\n"
            "connection - Test LM Studio API connectivity and display ping.\n"
            "setcolor - Customize message colors. Usage: !setcolor <role> <color>\n"
            "characterlist [remake] - List all characters with one-sentence summaries (pass 'remake' to regenerate them).\n"
            "character - Switch to a specific character (auto-saves current conversation).\n"
            "exit - Save conversation and exit the tool.\n"
            "help - Display this help message."
        )
        command_output(channel, help_msg)
        return True
    return False

def process_commands(channel, sender, command, argument, sock_file, active_users):
    if process_commands_section1(channel, sender, command, argument, sock_file, active_users):
        return
    if process_commands_section3(channel, sender, command, argument, sock_file):
        return
    if process_commands_section4(channel, sender, command, argument, sock_file, active_users):
        return
    command_output(channel, "Unknown command. Type !help for a list of commands.")

#############################################
# Main Command-Line Interface Loop
#############################################

def main():
    global current_channel, SYS_MODEL, CONVO_MODEL, username, server_status
    for folder in [BASE_FOLDER, CHARACTERS_FOLDER, SAVED_CONVOS_FOLDER, CONVERSATIONS_FOLDER]:
        if not os.path.exists(folder):
            os.makedirs(folder)

    if os.path.exists(USERNAME_FILE):
        with open(USERNAME_FILE, "r", encoding="utf-8") as f:
            username = f.read().strip()
    else:
        username = input("Enter your username: ").strip()
        with open(USERNAME_FILE, "w", encoding="utf-8") as f:
            f.write(username)
    
    server_status = test_connection()
    command_output("#welcome", server_status)
    
    welcome_msg = f"Welcome to Velvet's (py)chai version {VERSION}! Logged in as {username}."
    command_output("#welcome", welcome_msg)

    current_channel = "#welcome"
    load_conversation_history(current_channel)
    command_output(current_channel, f"Switched to default character channel: {current_channel}")
    command_output(current_channel, "Type !help for list of commands.")

    while True:
        try:
            prompt_str = f"[{current_channel}] {username} > "
            user_input = input(prompt_str)
        except EOFError:
            command_output(current_channel, "EOF encountered. Exiting interactive mode.")
            break
        except KeyboardInterrupt:
            command_output(current_channel, "KeyboardInterrupt received. Exiting.")
            break
        user_input = user_input.strip()
        if not user_input:
            continue

        if current_channel in confirmation_pending:
            if process_confirmation_response(current_channel, "User", user_input, None):
                continue

        if current_channel in multi_input_pending:
            pending = multi_input_pending[current_channel]
            if user_input.lower() == "cancel":
                multi_input_pending.pop(current_channel, None)
                command_output(current_channel, "Multiline input cancelled.")
                continue
            if pending["command"] == "questionset" and pending.get("single_line_first", False) and pending["question_index"] == 0:
                pending.setdefault("answers", []).append(user_input.strip())
                pending["buffer"] = ""
                pending["question_index"] += 1
                if pending["question_index"] < len(pending["questions"]):
                    next_q = pending["questions"][pending["question_index"]]
                    command_output(current_channel, next_q + " (type your answer then 'continue' when done or 'cancel' to abort)")
                else:
                    details = pending["answers"]
                    ai_query = CUSTOM_QUESTIONSET_PROMPT + "\n" + (
                        f"Name: {details[0]}\n"
                        f"Background: {details[1]}\n"
                        f"Personality: {details[2]}\n"
                        f"Special Abilities/Additional Details: {details[3]}\n"
                        f"Extra Instructions: {details[4]}"
                    )
                    response = run_with_progress("Generating Backstory", lambda: requests.post(get_lm_api_url(), json={"model": SYS_MODEL, "messages": [{"role": "user", "content": ai_query}], "stream": False}, headers={"Content-Type": "application/json"}))
                    if response.status_code == 200:
                        data = response.json()
                        new_prompt = process_reply(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                        if new_prompt:
                            if current_channel in conversation_histories and conversation_histories[current_channel]:
                                conversation_histories[current_channel][0]["content"] = new_prompt
                            else:
                                conversation_histories[current_channel] = [{"role": "system", "content": new_prompt}]
                            char_name = current_channel.lstrip("#")
                            with open(os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt"), "w", encoding="utf-8") as f:
                                f.write(new_prompt)
                            command_output(current_channel, "Questionset prompt updated and backstory set.")
                        else:
                            command_output(current_channel, "LM Studio API returned an empty prompt for questionset.")
                    else:
                        command_output(current_channel, f"LM Studio API error during questionset: {response.status_code}")
                    multi_input_pending.pop(current_channel, None)
                continue

            if user_input.lower() == "continue":
                if pending["command"] == "set":
                    complete_input = pending.get("buffer", "").strip()
                    ai_prompt = CUSTOM_SET_PROMPT + "\nDetails: " + complete_input
                    response = run_with_progress("Generating Backstory", lambda: requests.post(get_lm_api_url(), json={"model": SYS_MODEL, "messages": [{"role": "user", "content": ai_prompt}]}, headers={"Content-Type": "application/json"}))
                    if response.status_code == 200:
                        data = response.json()
                        new_prompt = process_reply(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                        if new_prompt:
                            if current_channel in conversation_histories and conversation_histories[current_channel]:
                                conversation_histories[current_channel][0]["content"] = new_prompt
                            else:
                                conversation_histories[current_channel] = [{"role": "system", "content": new_prompt}]
                            char_name = current_channel.lstrip("#")
                            with open(os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt"), "w", encoding="utf-8") as f:
                                f.write(new_prompt)
                            command_output(current_channel, "System prompt updated via set command.")
                        else:
                            command_output(current_channel, "LM Studio API returned an empty prompt for set.")
                    else:
                        command_output(current_channel, f"LM Studio API error during set: {response.status_code}")
                    multi_input_pending.pop(current_channel, None)
                elif pending["command"] == "questionset":
                    pending.setdefault("answers", []).append(pending.get("buffer", "").strip())
                    pending["buffer"] = ""
                    pending["question_index"] += 1
                    if pending["question_index"] < len(pending["questions"]):
                        next_q = pending["questions"][pending["question_index"]]
                        command_output(current_channel, next_q + " (type your answer then 'continue' when done or 'cancel' to abort)")
                    else:
                        details = pending["answers"]
                        ai_query = CUSTOM_QUESTIONSET_PROMPT + "\n" + (
                            f"Name: {details[0]}\n"
                            f"Background: {details[1]}\n"
                            f"Personality: {details[2]}\n"
                            f"Special Abilities/Additional Details: {details[3]}\n"
                            f"Extra Instructions: {details[4]}"
                        )
                        response = run_with_progress("Generating Backstory", lambda: requests.post(get_lm_api_url(), json={"model": SYS_MODEL, "messages": [{"role": "user", "content": ai_query}], "stream": False}, headers={"Content-Type": "application/json"}))
                        if response.status_code == 200:
                            data = response.json()
                            new_prompt = process_reply(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                            if new_prompt:
                                if current_channel in conversation_histories and conversation_histories[current_channel]:
                                    conversation_histories[current_channel][0]["content"] = new_prompt
                                else:
                                    conversation_histories[current_channel] = [{"role": "system", "content": new_prompt}]
                                char_name = current_channel.lstrip("#")
                                with open(os.path.join(CHARACTERS_FOLDER, f"{char_name}.txt"), "w", encoding="utf-8") as f:
                                    f.write(new_prompt)
                                command_output(current_channel, "Questionset prompt updated and backstory set.")
                            else:
                                command_output(current_channel, "LM Studio API returned an empty prompt for questionset.")
                        else:
                            command_output(current_channel, f"LM Studio API error during questionset: {response.status_code}")
                        multi_input_pending.pop(current_channel, None)
                elif pending["command"] == "dialogue":
                    complete_input = pending.get("buffer", "").strip()
                    load_conversation_history(current_channel)
                    conversation_histories[current_channel].append({"role": "user", "content": complete_input})
                    payload = {"model": CONVO_MODEL, "messages": conversation_histories[current_channel], "stream": True}
                    process_api_request_stream(current_channel, payload, None)
                    multi_input_pending.pop(current_channel, None)
                continue
            else:
                pending["buffer"] = pending.get("buffer", "") + "\n" + user_input
                command_output(current_channel, "Current multiline input:\n" + pending["buffer"])
                continue

        if user_input.startswith("!"):
            parts = user_input[1:].split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            if cmd == "character":
                save_conversation(current_channel)
                if arg.strip():
                    new_channel = "#" + arg.strip()
                    char_file = os.path.join(CHARACTERS_FOLDER, f"{arg.strip()}.txt")
                    current_channel = new_channel
                    load_conversation_history(current_channel)
                    if not os.path.exists(char_file):
                        command_output(current_channel, f"Warning: Character file for '{arg.strip()}' does not exist. Using default prompt.")
                    command_output(current_channel, f"Switched to character '{arg.strip()}'.")
                else:
                    command_output(current_channel, "Usage: !character {name}")
                continue
            process_commands(current_channel, "User", cmd, arg, None, None)
            continue

        # Append the user input (formatted) to the conversation history.
        conversation_histories[current_channel].append({"role": "user", "content": user_input})
        conversation_output(current_channel, "user", user_input)
        # Send request with streaming; block input until complete.
        payload = {"model": CONVO_MODEL, "messages": conversation_histories[current_channel], "stream": True}
        process_api_request_stream(current_channel, payload, None)

if __name__ == "__main__":
    main()
