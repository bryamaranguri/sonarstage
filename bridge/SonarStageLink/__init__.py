"""SonarStage Link: Remote Script that lets SonarStage drive Ableton Live 12."""


def create_instance(c_instance):
    # imported here: `Live` and `ableton` only exist inside Ableton, and core.py must
    # stay importable for tests
    from .surface import SonarStageLink
    return SonarStageLink(c_instance)
