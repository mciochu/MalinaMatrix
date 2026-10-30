"""Copy this file to add an optional background module.

Required contract:
- create(settings) -> service object
- service.run(stop_event) -> optional blocking worker loop
- optional service.close() -> release resources

This extension is loaded only when its name is listed in [extensions] modules.
The runtime starts it on a daemon worker, not on the LED drawing loop.
"""
class ExampleModule:
    def run(self, stop_event):
        stop_event.wait()


def create(settings):
    return ExampleModule()
