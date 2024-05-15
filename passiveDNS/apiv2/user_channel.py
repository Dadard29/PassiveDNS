from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime

from channels.email import MailSendingError
from channels.send import send
from channels.telegram import TelegramSendingError
from channels.templates_list import CHANNEL_VERIFY_TEMPLATE, TEST_TEMPLATE
from apiv2.auth import get_current_user
from db.database import ObjectNotFound
from models.channel import Channel
from models.user_channel import UserChannel
from models.user import User
from utils import config, timezone

users_channel_router = APIRouter()

class UserChannelCreate(BaseModel):
    contact: str

class UserChannelUpdate(BaseModel):
    token: str


# get the list of channels setup by the user
@users_channel_router.get("/user/channels")
def users_channel_list(user: User=Depends(get_current_user)):
    username = user.username

    ch_list = []
    user_channels = UserChannel.list_from_username(username)
    for u_ch in user_channels:
        channel = Channel.get(u_ch.channel_name)
        ch_list.append({
            "user_channel": u_ch,
            "channel": channel
        })

    # return the list of channels edges and their corresponding channel
    out = [
        {
            "user_channel": o["user_channel"].safe_json(),
            "channel": o["channel"].safe_json()
        }
        for o in ch_list
    ]

    return {
        "msg": "user linked channels list retrieved",
        "channel_list": out

    }

@users_channel_router.get("/user/channels/{channel_name}")
def user_channel_get(channel_name, user: User=Depends(get_current_user)):
    username = user.username
    try:
        user_channel = UserChannel.get(username, channel_name)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="user channel not found")
    
    return {
        "msg": f"user channel retrieved",
        "user_channel": user_channel.safe_json(),
    }

@users_channel_router.post("/user/channels/{channel_name}")
def user_channel_create(channel_name, data: UserChannelCreate, user: User=Depends(get_current_user)):
    new_user_channel = None
    username = user.username
    
    contact = data.contact
    try:
        channel = Channel.get(channel_name)
        user = User.get(username)
    except ObjectNotFound as o:
        raise HTTPException(status_code=404, detail=str(o))

    if UserChannel.exists(user.username, channel.name):
        raise HTTPException(status_code=500, detail="this channel is already linked")

    new_user_channel = UserChannel.new(user.username, channel.name, contact)
    new_user_channel.insert()

    template = CHANNEL_VERIFY_TEMPLATE
    template.set_format(token=new_user_channel.token, channel=channel.name)
    try:
        send(contact, channel, template)
    except (MailSendingError, TelegramSendingError):
        if new_user_channel is not None:
            new_user_channel.delete()

        raise HTTPException(status_code=500, detail="error sending token to this contact")
    
    return {
        "msg": f"linked channel with user {new_user_channel.username}",
        "user_channel": new_user_channel.safe_json()
    }


@users_channel_router.put("/user/channels/{channel_name}")
def user_channel_verify(channel_name, data: UserChannelUpdate, user: User=Depends(get_current_user)):
    
    username = user.username
    token = data.token

    try:
        user_channel = UserChannel.get(username, channel_name)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="user channel not found")
    
    if user_channel.verified:
        raise HTTPException(status_code=500, detail="this channel has already been verified")

    if token != user_channel.token:
        raise HTTPException(status_code=500, detail="invalid token")

    user_channel.update(verified=True)
    return {
        "msg": f"channel contact verified",
        "user_channel": user_channel.safe_json()
    }


@users_channel_router.delete("/user/channels/{channel_name}")
def user_channel_delete(channel_name, user: User=Depends(get_current_user)):
    username = user.username
    
    if channel_name == Channel.DEFAULT:
        raise HTTPException(status_code=500, detail="cannot unlink default channel")
    
    try:
        user_channel = UserChannel.get(username, channel_name)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="user channel not found")
    
    user_channel.delete()
    return {
        "msg": f"user channel deleted",
        "user_channel": user_channel.safe_json()
    }


@users_channel_router.get("/user/channels/{channel_name}/test")
def channel_test(channel_name, user: User=Depends(get_current_user)):
    
    username = user.username
    try:
        user = User.get(username)
        channel = Channel.get(channel_name)
        user_channel = UserChannel.get(user.username, channel.name)

        template = TEST_TEMPLATE
        date = timezone.get_current_datetime(config.g.TIMEZONE)
    except ObjectNotFound:
        raise HTTPException(status_code=404, detail="object not found")
    
    template.set_format(date=str(date))
    
    try:
        send(user_channel.contact, channel, template)
    except (MailSendingError, TelegramSendingError):
        raise HTTPException(status_code=500, detail="failed to send test")

    return {
        "msg": f"user channel tested",
        "user_channel": user_channel.safe_json()
    }

