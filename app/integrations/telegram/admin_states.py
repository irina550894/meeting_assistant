from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    custom_meeting_url = State()
    rejection_reason = State()
    user_message = State()
