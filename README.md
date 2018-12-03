Gorrabot is a Gitlab bot made to automate checks and proccesses in the Faraday
development.

# Features

## <a name="changelog-check"></a>Check that the CHANGELOG is modified

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

Get the issue related to a merge request by inspecting its source branch name
(e.g `tkt_***REMOVED***_1234_some_description`). Then, when the status of the MR is
updated, also update the labels and status of the related issue.

Example actions (see the code of `sync_related_issue` `app.py` for the exact
list):

* Created WIP MR -> Label issue as accepted
* Pending merge/approbal MR -> Label issue as test
* Merged MR -> Close issue and delete status labels (accepted, test)
* Closed MR -> Delete status labels (set to new)

<a name="multiple-merge-requests"></a>
Sometimes this actions aren't desired, like for example when an issue
requires multiple merge requests merged to be considered as fixed.
In this case, you can add the `multiple-merge-requests` to the issue
and its status and labels won't be modified by gorrabot.

## Merge request field completion based on its issue

If a merge request doesn't have an assigned user, derive it from the assigned
user of its related issue. Do the same with the MR's milestone.

## Branch naming nomenclature check

If the source branch of a merge request doesn't match our nomenclature,
note that in a comment. The merge request won't be set to WIP because
of this, it is just a warning to avoid doing this the next time.

## Merge request title check

When creating a merge request from the gitlab web, by default it derives its
title from the source branch name. This is useful in many projects, but in
Faraday it can be annoying because of our branch naming conventions.

For example, it wouldn't be useful to have a merge request titled `Tkt ***REMOVED***
1234 some description`. A more concise title would be more helpful. If we
wanted, we could know the related issue and target version just by looking at
the source and target branches of the MR.

# Summary of special labels

* `no-changelog`: Use this when the merge request consist of a really
  small check that shouldn't be reflected on the `RELEASE.md` file
  See [this](#changelog-checks) for more documentation about this
* `multiple-merge-requests`: The only label that must be applied to issues
  instead of merge requests. Avoid gorrabot changing the status and labels of
  issues labeled with this. See [this](#multiple-merge-requests) for more
  information
* `sacate-la-gorra`: A wildcard label that totally disables gorrabot on
  that merge request. THIS ISN'T RECOMMENDED, SO THINK TWICE WHEN USING THIS
