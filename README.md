Gorrabot is a Gitlab bot made to automate checks and proccesses in the Faraday
development.

# Features

## Check that the CHANGELOG is modified

By default, merge requests MUST create a `.md` file inside the
`CHANGELOG/<current_version>` folder. We do this because it is easier to write
changelog messages after finishing working on the change than before releasing
a new version. In the latter, we could easily forget what we did and write a
lower quality changelog message.

When somebody publishes a ready to merge MR that didn't touch the changelog,
gorrabot automaticaly sets it to WIP (work in proccess). Then the MR's author
is required to touch the changelog, push a new commit and resolve the WIP
status from the gitlab web.

Alternatively, if the MR's author doesn't consider useful to add a changelog
entry for that change (e.g. when fixing typos or doing small refactors), he/she
can add the `no-changelog` entry to it request and this check won't be
performed to that merge request.

## Issue state changing based on MR status

TODO

## Merge request field completion based on its issue

TODO

## Merge request title check

TODO

## Branch naming nomenclature check

TODO

# Special labels

TODO
