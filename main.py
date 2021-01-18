import sys
import asyncio

import requests
import websockets
import json

import yaml

config = yaml.load(open('config.yaml', 'r'), Loader=yaml.Loader)
credentials = yaml.load(open('credentials.yaml', 'r'), Loader=yaml.Loader)

GLIMESH_API = "https://glimesh.tv/api"

GLIMESH_WS = f"wss://glimesh.tv/api/socket/websocket?vsn=2.0.0&client_id={credentials['client_id']}"

command_to_key = config['commands']
admin_command_to_key = config['admin_commands']
commands_queue = []

websocket = None
subscription_id = None

if sys.platform == 'linux':
    from xdo import Xdo

    xdo = Xdo()
    window_id = xdo.search_windows(config['window_title'].encode())[0]
    print(f'XDO: Found window {window_id} for title {config["window_title"]}')

async def connect_websocket_and_subscribe():
    global websocket
    print('WS: Connecting to glimesh.tv...')
    websocket = await websockets.connect(GLIMESH_WS)
    await websocket.send(json.dumps(["1","1","__absinthe__:control","phx_join",{}]))
    resp = json.loads(await websocket.recv())[4]
    if resp['status'] == 'ok':
        print('WS: Connected and authenticated successfully, subscribing to chat')

        subscribe_data = {
            "query": f"subscription{{ chatMessage(channelId: {config['channel_id']}) {{ user {{ username }} message }} }}",
            "variables" : {}
        }

        await websocket.send(json.dumps(["1","1","__absinthe__:control","doc",subscribe_data]))
        resp = json.loads(await websocket.recv())[4]
        print(resp)
        if resp['status'] == 'ok':
            global subscription_id
            subscription_id = resp['response']['subscriptionId']

loop = asyncio.get_event_loop()
loop.run_until_complete(connect_websocket_and_subscribe())

async def send_heartbeat():
    while True:
        await asyncio.sleep(30)
        # print('WS: Sending heartbeat')
        await websocket.send(json.dumps(["1","1","phoenix","heartbeat",{}]))

async def retrieve_data():
    while True:
        resp = json.loads(await websocket.recv())
        if resp[2] == subscription_id and 'data' in resp[4]['result']:
            chat_message = resp[4]['result']['data']['chatMessage']['message'].lower()
            user = resp[4]['result']['data']['chatMessage']['user']['username']
            print(user+':', chat_message)
            if chat_message in command_to_key:
                commands_queue.append(chat_message)
            elif chat_message.startswith('!'):
                # Administrator commands
                chat_message = chat_message[1:]
                if user in config['admins']:
                    if chat_message in admin_command_to_key:
                        commands_queue.append(chat_message)
            elif '+' in chat_message:
                error = False
                commands = chat_message.replace(' ', '').split('+')
                if len(commands) > 3:
                    # We don't allow more than 3 simutinious inputs, ignore.
                    error = True
                for command in commands:
                    if command not in command_to_key:
                        # One of the commands not on the dictionary, ignore entirely.
                        error = True
                        break
                if not error:
                    commands_queue.append(commands)
            await asyncio.sleep(0)

async def do_inputs():
    while True:
        if not commands_queue:
            # Empty
            await asyncio.sleep(0)
            continue
        command = commands_queue.pop(0)
        if type(command) is str:
            keystroke = command_to_key.get(command)
            if command in admin_command_to_key:
                keystroke = admin_command_to_key.get(command)
            if not keystroke:
                print(f'Keystroke undefined for command {command}. Ignoring.')
                await asyncio.sleep(0)
                continue
        elif type(command) is list:
            keystroke = ''
            for comm in command:
                stroke = command_to_key.get(comm)
                if not stroke:
                    print(f'Keystroke undefined for command {comm}. Ignoring.')
                    await asyncio.sleep(0)
                    continue
                keystroke += "+" + stroke

        if sys.platform == 'linux':
            xdo.send_keysequence_window_down(window_id, keystroke.encode(), 0)
            await asyncio.sleep(1)
            xdo.send_keysequence_window_up(window_id, keystroke.encode(), 0)

loop.create_task(send_heartbeat())
loop.create_task(retrieve_data())
loop.create_task(do_inputs())

loop.run_forever()
