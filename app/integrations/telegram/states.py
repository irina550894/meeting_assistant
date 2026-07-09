from aiogram.fsm.state import State, StatesGroup


class UserBookingStates(StatesGroup):
    consent = State()
    name = State()
    email = State()
    meeting_type = State()
    duration = State()
    date = State()
    time = State()
    comment = State()
    review = State()
    my_bookings = State()
    cancel_confirmation = State()
