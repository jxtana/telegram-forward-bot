#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import sys
import telepot
import time
import logging

from logging.config import fileConfig

from telepot.loop import MessageLoop
from telepot.exception import TelegramError

chats = {}
chat_config = {}
TOKEN = ""
PASSWORD = "changeme"

def load_from_files():
    global chats
    global chat_config
    
    if not os.path.isfile('chats.json'):
        save_status({})

    if not os.path.isfile('chat_config.json'):
        save_chat_config({})

    with open('chats.json', 'r') as f:
        chats = json.load(f)

    with open('chat_config.json', 'r') as f:
        chat_config = json.load(f)


def save_data(name, obj):
 
    if os.path.isfile(name +".bak"):
        os.remove(name +".bak")
    os.rename(os.path.realpath(name), os.path.realpath(name)+".bak")

    with open(name, 'w') as f:
        f.write(json.dumps(obj, indent =4, sort_keys=True))

def save_chat_config(obj):
    save_data('chat_config.json', obj)

def save_status(obj):
    save_data('chats.json',obj)

def get_chat_config_data(id, key, default):
    if not str(id) in chat_config:    
        return default
    if not key in chat_config[str(id)]:
        return default
    return chat_config[str(id)][key]
    
def chat_config_update(id, data, name):
    if not str(id) in chat_config:
        chat_config[str(id)] = {}
    chat_config[str(id)].update(data)
    chat_config[str(id)].update({ 'name' : name})
    save_chat_config(chat_config)


def is_allowed(msg):
    if msg['chat']['type'] == 'channel':
        return True #all channel admins are allowed to use the bot (channels don't have sender info)

    if 'from' in msg:
        return get_chat_config_data(msg['from']['id'], 'allowed', False)
    return False

def get_name(msg):
    if msg['chat']['type'] == "private":
        return "Personal chat with " + msg['chat']['first_name'] + ((" " + msg['chat']['last_name']) if 'last_name' in msg['chat'] else "")
    else:
        return msg['chat']['title']

def delete_source_message(chat_id,msg):
    keep = msg['chat']['type'] == 'private' or get_chat_config_data(chat_id, 'keepMessages', False)
    if not keep:
        try:
            bot.deleteMessage(telepot.message_identifier(msg))
        except TelegramError as ex:
            logging.error("Unable to delete source message : " + str(ex) + " " + str(msg))

def cmd_addme(chat_id, msg, txt):
    if msg['chat']['type'] != 'private':
        bot.sendMessage(chat_id, "This command is meant to be used only on personal chats.")
        delete_source_message(chat_id,msg)
    else:
        used_password = " ".join(txt.strip().split(" ")[1:])
        if used_password == PASSWORD:
            chat_config_update(msg['from']['id'], { 'allowed' : True } , get_name(msg) )
            bot.sendMessage(chat_id, msg['from']['first_name'] + ", you have been registered " +
                            "as an authorized user of this bot.")
        else:
            logging.error("Wrong password : " + str(msg))
            bot.sendMessage(chat_id, "Wrong password.")

def cmd_add_tag(chat_id, msg, txt):
    txt_split = txt.strip().split(" ")
    if len(txt_split) == 2 and "#" == txt_split[1][0]:
        tag = txt_split[1].lower()
        name = get_name(msg)
        chats[tag] = {'id': chat_id, 'name' : name}
        bot.sendMessage(chat_id, name + " added with tag " + tag)
        save_status(chats)
        delete_source_message(chat_id,msg)
    else:
        bot.sendMessage(chat_id, "Incorrect format. It should be _/add #{tag}_", parse_mode="Markdown")


def cmd_rm_tag(chat_id, msg, txt):
    txt_split = txt.strip().split(" ")
    if len(txt_split) == 2 and "#" == txt_split[1][0]:
        tag = txt_split[1].lower()
        if tag in chats:
            if chats[tag]['id'] == chat_id:
                del chats[tag]
                bot.sendMessage(chat_id, "Tag "+tag+" deleted from taglist.")
                save_status(chats)
            else:
                bot.sendMessage(chat_id, "You can't delete a chat's tag from a different chat.")
        else:
            bot.sendMessage(chat_id, "Tag doesn't exist on TagList")
    else:
        bot.sendMessage(chat_id, "Incorrect format. It should be _/rm #{tag}_", parse_mode="Markdown")


def do_forward(chat_id, msg, txt, fwd_tags):
    txt_split =txt.strip().split(" ")

    i = 0
    while i < len(txt_split) and txt_split[i][0] == "#":
        fwd_tags.append(txt_split[i].lower())
        i+=1
                
    if i != len(txt_split) or 'reply_to_message' in msg:        
        approved = []
        rejected = []

        caption = get_chat_config_data(chat_id, "caption", "")

        for tag in fwd_tags:
            if tag in chats:
                if chats[tag]['id'] != chat_id:
                    approved.append(chats[tag]['name'])
                    if caption != "":
                        bot.sendMessage(chats[tag]['id'], caption)
         
                    if not 'reply_to_message' in msg or i != len(txt_split):
                        bot.forwardMessage(chats[tag]['id'], chat_id, msg['message_id'])
                    if 'reply_to_message' in msg:
                        bot.forwardMessage(chats[tag]['id'], chat_id, msg['reply_to_message']['message_id'])
                    if i == len(txt_split):
                        delete_source_message(chat_id, msg)            
            else:
                rejected.append(tag)

        if len(rejected) > 0:
            bot.sendMessage(chat_id, "Failed to send messages to tags <i>" + ", ".join(rejected) + "</i>", parse_mode="HTML")
    else:
        # Send Failed message to user to don't flood the group
        if 'from' in msg:
            bot.sendMessage(msg['from']['id'], "Failed to send a message only with tags which is not a reply to another message : " + txt)
        else:
            bot.sendMessage(chat_id, "Failed to send a message only with tags which is not a reply to another message" )




def handle(msg):
    logging.debug("Message: " + str(msg))
    # Add person as allowed
    content_type, chat_type, chat_id = telepot.glance(msg)
    txt = ""
    if 'text' in msg:
        txt = txt + msg['text']
    elif 'caption' in msg:
        txt = txt + msg['caption']
        
    # Commands that are valid only on groups and personal chats.
    if msg['chat']['type'] != 'channel':
        if "/addme" == txt.strip()[:6]:
            cmd_addme(chat_id, msg, txt)
            return
        elif is_allowed(msg):
            if "/rmme" == txt.strip()[:5]:
                chat_config_update(msg['from']['id'], { 'allowed' : False } , get_name(msg) )
                bot.sendMessage(chat_id, "Your permission for using the bot was removed successfully.")
                return
            elif "/chatlist" ==  txt.strip():
                response = "<b>Chat List</b>"
                for id in chat_config.keys():
                    config = chat_config[id]
                    response = response + "\n<b>" + str(id) + "</b>: <i>" + str(config) + "</i>"
                bot.sendMessage(chat_id, response, parse_mode="HTML")
                return
            elif "/taglist" ==  txt.strip():
                tags_names = []
                for tag, chat in chats.items():
                    tags_names.append( (tag, chat['name']))
                response = "<b>TagList</b>"
                for (tag, name) in sorted(tags_names):
                    response = response + "\n<b>" + tag + "</b>: <i>" + name + "</i>"
                bot.sendMessage(chat_id, response, parse_mode="HTML")
                return
            elif "/reload" == txt.strip():
                load_from_files()
                return
            
    if is_allowed(msg) and txt != "":
        fwd_tags = []
        if str(chat_id) in chat_config:
            if 'autofwd' in chat_config[str(chat_id)]:
                autofwd = chat_config[str(chat_id)]["autofwd"].split(" ")
                fwd_tags.extend(autofwd) 

        if "/add " == txt[:5]:
            cmd_add_tag(chat_id, msg, txt)
            delete_source_message(chat_id, msg)
                
        elif "/rm " == txt[:4]:
            cmd_rm_tag(chat_id, msg, txt)
            delete_source_message(chat_id, msg)
            
        elif "/fwdcaption " == txt.strip()[:12]:
            txt_split = txt.strip().split(" ")
            chat_config_update(chat_id,  { 'caption' : " ".join(txt_split[1:]) }, get_name(msg))
            delete_source_message(chat_id, msg)

        elif "/autofwd " == txt.strip()[:9]:
            txt_split = txt.strip().split(" ")
            chat_config_update(chat_id, { 'autofwd' : " ".join(txt_split[1:]).lower().strip() }, get_name(msg))
            delete_source_message(chat_id, msg)

        elif "#" == txt[0] or len(fwd_tags) > 0:
            do_forward(chat_id, msg, txt, fwd_tags)

def handle_with_try(msg):
    try:
       handle(msg)
    except Exception as ex:
       logging.exception("Error")




fileConfig('bot_logging.ini')
        
load_from_files()

if os.path.isfile('config.json'):
    with open('config.json', 'r') as f:
        config = json.load(f)
        if config['token'] == "":
            sys.exit("No token defined. Define it in a file called config.json.")
        if config['password'] == "":
            logging.warning("Empty Password for registering to use the bot." +
                  " It could be dangerous, because anybody could use this bot" +
                  " and forward messages to the channels associated to it")
        TOKEN = config['token']
        PASSWORD = config['password']
else:
    sys.exit("No config file found. Remember changing the name of config-sample.json to config.json")

bot = telepot.Bot(TOKEN)

MessageLoop(bot, handle_with_try).run_as_thread()
logging.info('Listening ...')
# Keep the program running.
while 1:
    time.sleep(10)


