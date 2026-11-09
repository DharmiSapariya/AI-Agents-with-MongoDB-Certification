# Resuming change streams

A MongoDB change stream event carries a resume token. Save the token after
processing the event successfully. A client that restarts can pass the last
saved token as resumeAfter to continue watching for events. The token must
still refer to history the deployment can access.
