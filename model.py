from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    user_id: int
    language: str
    fluency: int


class WorkingQueue:
    def __init__(self):
        self.users_in_queue = set()

    @property
    def user_ids_in_queue(self):
        return list([user.user_id for user in self.users_in_queue])

    def find_match(self, user_id) -> int | None:
        for uid in self.user_ids_in_queue:
            if uid != user_id:
                return uid
        return None

    def add_user(self, user: User):
        if user not in self.users_in_queue:
            self.users_in_queue.add(user)

    def remove_user(self, user: User):
        if user in self.users_in_queue:
            self.users_in_queue.remove(user)


working_queue = WorkingQueue()
