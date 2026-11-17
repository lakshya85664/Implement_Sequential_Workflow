stateDiagram-v2
    [*] --> created
    created --> running: start
    running --> waiting: pause
    waiting --> running: resume
    running --> completed: complete
    running --> needs_review: review
    running --> failed: fail
    waiting --> failed: fail
    needs_review --> running: resume
    completed --> [*]
    failed --> [*]