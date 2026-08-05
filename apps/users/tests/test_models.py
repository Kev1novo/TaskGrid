from apps.users.models import User


def test_is_admin_true_for_admin_role():
    user = User(username="alice", role=User.Role.ADMIN)
    assert user.is_admin() is True


def test_is_admin_false_for_user_role():
    user = User(username="alice", role=User.Role.USER)
    assert user.is_admin() is False


def test_is_admin_true_for_superuser():
    user = User(username="alice", role=User.Role.USER, is_superuser=True)
    assert user.is_admin() is True
