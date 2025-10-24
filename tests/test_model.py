from model import working_queue, User


def test_create_user():
    new_user = User(123, "english", 0)
    assert new_user.user_id == 123
    assert new_user.language == "english"
    assert new_user.fluency == 0

def test_working_queue():
    assert hasattr(working_queue, "users_in_queue")

def test_add_user_to_queue():
    new_user = User(123, "english", 0)
    working_queue.add_user(new_user)
    working_queue.add_user(new_user)
    assert len(working_queue.users_in_queue) == 1
    assert new_user in working_queue.users_in_queue\

def test_remove_user_from_queue():
    new_user = User(123, "english", 0)
    working_queue.add_user(new_user)
    working_queue.remove_user(new_user)
    assert new_user not in working_queue.users_in_queue

def test_find_match():
    user1 = User(123, "english", 0)
    user2 = User(124, "english", 0)
    working_queue.add_user(user1)
    working_queue.add_user(user2)
    result = working_queue.find_match(124)
    assert result == 123

