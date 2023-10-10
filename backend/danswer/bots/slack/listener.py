import re
import time
from typing import Any
from typing import cast

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from sqlalchemy.orm import Session

from danswer.bots.slack.config import get_slack_bot_config_for_channel
from danswer.bots.slack.constants import SLACK_CHANNEL_ID
from danswer.bots.slack.handlers.handle_feedback import handle_slack_feedback
from danswer.bots.slack.handlers.handle_message import handle_message
from danswer.bots.slack.models import SlackMessageInfo
from danswer.bots.slack.tokens import fetch_tokens
from danswer.bots.slack.utils import ChannelIdAdapter
from danswer.bots.slack.utils import decompose_block_id
from danswer.bots.slack.utils import get_channel_name_from_id
from danswer.bots.slack.utils import respond_in_thread
from danswer.configs.app_configs import DANSWER_BOT_RESPOND_EVERY_CHANNEL
from danswer.configs.app_configs import DANSWER_REACT_EMOJI
from danswer.connectors.slack.utils import make_slack_api_rate_limited
from danswer.db.engine import get_sqlalchemy_engine
from danswer.dynamic_configs.interface import ConfigNotFoundError
from danswer.utils.logger import setup_logger


logger = setup_logger()


class MissingTokensException(Exception):
    pass


def _get_socket_client() -> SocketModeClient:
    # For more info on how to set this up, checkout the docs:
    # https://docs.danswer.dev/slack_bot_setup
    try:
        slack_bot_tokens = fetch_tokens()
    except ConfigNotFoundError:
        raise MissingTokensException("Slack tokens not found")
    return SocketModeClient(
        # This app-level token will be used only for establishing a connection
        app_token=slack_bot_tokens.app_token,
        web_client=WebClient(token=slack_bot_tokens.bot_token),
    )


def prefilter_requests(req: SocketModeRequest, client: SocketModeClient) -> bool:
    """True to keep going, False to ignore this Slack request"""
    if req.type == "events_api":
        # Verify channel is valid
        event = cast(dict[str, Any], req.payload.get("event", {}))
        msg = cast(str | None, event.get("text"))
        channel = cast(str | None, event.get("channel"))
        channel_specific_logger = ChannelIdAdapter(
            logger, extra={SLACK_CHANNEL_ID: channel}
        )

        # This should never happen, but we can't continue without a channel since
        # we can't send a response without it
        if not channel:
            channel_specific_logger.error("Found message without channel - skipping")
            return False

        if not msg:
            channel_specific_logger.error("Cannot respond to empty message - skipping")
            return False

        # Ensure that the message is a new message of expected type
        event_type = event.get("type")
        if event_type not in ["app_mention", "message"]:
            channel_specific_logger.info(
                f"Ignoring non-message event of type '{event_type}' for channel '{channel}'"
            )
            return False

        if event_type == "message":
            bot_tag_id = client.web_client.auth_test().get("user_id")
            if bot_tag_id and bot_tag_id in msg:
                # Let the tag flow handle this case, don't reply twice
                return False

        if event.get("bot_profile"):
            channel_specific_logger.info("Ignoring message from bot")
            return False

        # Ignore things like channel_join, channel_leave, etc.
        # NOTE: "file_share" is just a message with a file attachment, so we
        # should not ignore it
        message_subtype = event.get("subtype")
        if message_subtype not in [None, "file_share"]:
            channel_specific_logger.info(
                f"Ignoring message with subtype '{message_subtype}' since is is a special message type"
            )
            return False

        message_ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        # Pick the root of the thread (if a thread exists)
        if thread_ts and message_ts != thread_ts:
            channel_specific_logger.info(
                "Skipping message since it is not the root of a thread"
            )
            return False

        msg = cast(str, event.get("text", ""))
        if not msg:
            channel_specific_logger.error("Unable to process empty message")
            return False

    if req.type == "slash_commands":
        # Verify that there's an associated channel
        channel = req.payload.get("channel_id")
        channel_specific_logger = ChannelIdAdapter(
            logger, extra={SLACK_CHANNEL_ID: channel}
        )
        if not channel:
            channel_specific_logger.error(
                "Received DanswerBot command without channel - skipping"
            )
            return False

        sender = req.payload.get("user_id")
        if not sender:
            channel_specific_logger.error(
                "Cannot respond to DanswerBot command without sender to respond to."
            )
            return False

    return True


def process_feedback(req: SocketModeRequest, client: SocketModeClient) -> None:
    actions = req.payload.get("actions")
    if not actions:
        logger.error("Unable to process block actions - no actions found")
        return

    action = cast(dict[str, Any], actions[0])
    action_id = cast(str, action.get("action_id"))
    block_id = cast(str, action.get("block_id"))
    user_id = cast(str, req.payload["user"]["id"])
    channel_id = cast(str, req.payload["container"]["channel_id"])
    thread_ts = cast(str, req.payload["container"]["thread_ts"])

    handle_slack_feedback(
        block_id=block_id,
        feedback_type=action_id,
        client=client.web_client,
        user_id_to_post_confirmation=user_id,
        channel_id_to_post_confirmation=channel_id,
        thread_ts_to_post_confirmation=thread_ts,
    )

    query_event_id, _, _ = decompose_block_id(block_id)
    logger.info(f"Successfully handled QA feedback for event: {query_event_id}")


def build_request_details(
    req: SocketModeRequest, client: SocketModeClient
) -> SlackMessageInfo:
    if req.type == "events_api":
        event = cast(dict[str, Any], req.payload["event"])
        msg = cast(str, event["text"])
        channel = cast(str, event["channel"])
        tagged = event.get("type") == "app_mention"
        message_ts = event.get("ts")
        thread_ts = event.get("thread_ts")
        if tagged:
            logger.info("User tagged DanswerBot")
            bot_tag_id = client.web_client.auth_test().get("user_id")
            msg = re.sub(rf"<@{bot_tag_id}>\s", "", msg)

        return SlackMessageInfo(
            msg_content=msg,
            channel_to_respond=channel,
            msg_to_respond=cast(str, thread_ts or message_ts),
            sender=event.get("user") or None,
            bipass_filters=tagged,
            is_bot_msg=False,
        )

    elif req.type == "slash_commands":
        channel = req.payload["channel_id"]
        msg = req.payload["text"]
        sender = req.payload["user_id"]

        return SlackMessageInfo(
            msg_content=msg,
            channel_to_respond=channel,
            msg_to_respond=None,
            sender=sender,
            bipass_filters=True,
            is_bot_msg=True,
        )

    raise RuntimeError("Programming fault, this should never happen.")


def send_msg_ack_to_user(details: SlackMessageInfo, client: SocketModeClient) -> None:
    if details.is_bot_msg and details.sender:
        respond_in_thread(
            client=client.web_client,
            channel=details.channel_to_respond,
            thread_ts=details.msg_to_respond,
            receiver_ids=[details.sender],
            text="Hi, we're evaluating your query :face_with_monocle:",
        )
        return

    slack_call = make_slack_api_rate_limited(client.web_client.reactions_add)
    slack_call(
        name=DANSWER_REACT_EMOJI,
        channel=details.channel_to_respond,
        timestamp=details.msg_to_respond,
    )


def remove_react(details: SlackMessageInfo, client: SocketModeClient) -> None:
    if details.is_bot_msg:
        return

    slack_call = make_slack_api_rate_limited(client.web_client.reactions_remove)
    slack_call(
        name=DANSWER_REACT_EMOJI,
        channel=details.channel_to_respond,
        timestamp=details.msg_to_respond,
    )


def apologize_for_fail(
    details: SlackMessageInfo,
    client: SocketModeClient,
) -> None:
    respond_in_thread(
        client=client.web_client,
        channel=details.channel_to_respond,
        thread_ts=details.msg_to_respond,
        text="Sorry, we weren't able to find anything relevant :cold_sweat:",
    )


def process_message(
    req: SocketModeRequest,
    client: SocketModeClient,
    respond_every_channel: bool = DANSWER_BOT_RESPOND_EVERY_CHANNEL,
) -> None:
    logger.info(f"Received Slack request of type: '{req.type}'")

    # Throw out requests that can't or shouldn't be handled
    if not prefilter_requests(req, client):
        return

    details = build_request_details(req, client)
    channel = details.channel_to_respond
    channel_name = get_channel_name_from_id(
        client=client.web_client, channel_id=channel
    )

    engine = get_sqlalchemy_engine()
    with Session(engine) as db_session:
        slack_bot_config = get_slack_bot_config_for_channel(
            channel_name=channel_name, db_session=db_session
        )

    # Be careful about this default, don't want to accidentally spam every channel
    if slack_bot_config is None and not respond_every_channel:
        logger.info(
            "Skipping message since the channel is not configured to use DanswerBot"
        )
        return

    try:
        send_msg_ack_to_user(details, client)
    except SlackApiError as e:
        logger.error(f"Was not able to react to user message due to: {e}")

    failed = handle_message(
        message_info=details,
        channel_config=slack_bot_config,
        client=client.web_client,
    )

    # Skipping answering due to pre-filtering is not considered a failure
    if failed:
        apologize_for_fail(details, client)

    try:
        remove_react(details, client)
    except SlackApiError as e:
        logger.error(f"Failed to remove Reaction due to: {e}")


def acknowledge_message(req: SocketModeRequest, client: SocketModeClient) -> None:
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)


def process_slack_event(client: SocketModeClient, req: SocketModeRequest) -> None:
    # Always respond right away, if Slack doesn't receive these frequently enough
    # it will assume the Bot is DEAD!!! :(
    acknowledge_message(req, client)

    try:
        if req.type == "interactive" and req.payload.get("type") == "block_actions":
            return process_feedback(req, client)

        elif req.type == "events_api" or req.type == "slash_commands":
            return process_message(req, client)
    except Exception:
        logger.exception("Failed to process slack event")


# Follow the guide (https://docs.danswer.dev/slack_bot_setup) to set up
# the slack bot in your workspace, and then add the bot to any channels you want to
# try and answer questions for. Running this file will setup Danswer to listen to all
# messages in those channels and attempt to answer them. As of now, it will only respond
# to messages sent directly in the channel - it will not respond to messages sent within a
# thread.
#
# NOTE: we are using Web Sockets so that you can run this from within a firewalled VPC
# without issue.
if __name__ == "__main__":
    try:
        socket_client = _get_socket_client()
        socket_client.socket_mode_request_listeners.append(process_slack_event)  # type: ignore

        # Establish a WebSocket connection to the Socket Mode servers
        logger.info("Listening for messages from Slack...")
        socket_client.connect()

        # Just not to stop this process
        from threading import Event

        Event().wait()
    except MissingTokensException:
        # try again every 30 seconds. This is needed since the user may add tokens
        # via the UI at any point in the programs lifecycle - if we just allow it to
        # fail, then the user will need to restart the containers after adding tokens
        logger.debug("Missing Slack Bot tokens - waiting 60 seconds and trying again")
        time.sleep(60)
