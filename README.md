Gorrabot is a Gitlab bot made to automate checks and processes in the Faraday
development.

# Features

## <a name="changelog-check"></a>Check that the CHANGELOG is modified

By default, merge requests MUST create a `.md` file inside the
`CHANGELOG/<current_version>` folder. We do this because it is easier to write
changelog messages after finishing working on the change than before releasing
a new version. In the latter, we could easily forget what we did and write a
lower quality changelog message.

When somebody publishes a ready to merge MR that didn't touch the changelog,
gorrabot automaticaly sets it to WIP (work in process). Then the MR's author
is required to touch the changelog, push a new commit and resolve the WIP
status from the gitlab web.

Alternatively, if the MR's author doesn't consider useful to add a changelog
entry for that change (e.g. when fixing typos or doing small refactors), he/she
can add the `no-changelog` label to the merge request and this check won't be
performed to it.

## Issue state changing based on MR status

Get the issue related to a merge request by inspecting its source branch name
(e.g `tkt_community_1234_some_description`). Then, when the status of the MR is
updated, also update the labels and status of the related issue.

Gorrabot also adds a `Closes #1234` text in the description, so GitLab closes
the related issue when the MR is merged. Also, when a user sees the issue
details he/she will have a link to its corresponding merge request.

Example actions (see the code of `sync_related_issue` `app.py` for the exact
list):

* Created WIP MR -> Label issue as accepted
* Pending merge/approbal MR -> Label issue as test
* Merged MR -> Close issue and delete status labels (accepted, test)
* Closed MR -> Delete status labels (set to new)

<a name="multiple-merge-requests"></a>
Sometimes this actions aren't desired, like for example when an issue requires
multiple merge requests to be considered as fixed.  In this case, you can add
the `multiple-merge-requests` label to the issue and its status and labels
won't be modified by gorrabot.

## Merge request field completion based on its issue

If a merge request doesn't have an assigned user, derive it from the assigned
user of its related issue. Do the same with the MR's milestone.

## <a name="branch-nomenclature-check"></a>Branch naming nomenclature check

If the source branch of a merge request doesn't match our nomenclature,
note that in a comment. The merge request won't be set to WIP because
of this, it is just a warning to avoid doing this the next time.

## Merge request title check

When creating a merge request from the gitlab web, by default it derives its
title from the source branch name. This is useful in many projects, but in
Faraday it can be annoying because of our branch naming conventions.

For example, it wouldn't be useful to have a merge request titled `Tkt community
1234 some description`. A more concise title would be more helpful. If we
wanted, we could know the related issue and target version just by looking at
the source and target branches of the MR.

Like with the previous feature, this check will just leave a comment in the
merge request if doesn't pass, so the user could avoid this the next time.
There is no need to set it to WIP.

## Automatic creation of upper versions MRs

When a community feature MR also needs changes in professional, the suggested way to
proceed is to create a branch of professional/dev with both the changes of the community MR
and the specific changes to professional. Then, open another merge request with target
branch professional/dev.

Creating another merge request for the professional feature is tedious, so when the
user pushes the professional branch, Gorrabot will detect this is an "upper version
MR". Then, it will create a new MR with the same content as the community MR, but
with a `(professional edition)` added in the title to properly differentiate both MRs.

The same thing happens when a professional branch conflicts with upper branches (if exists).

Gorrabot will also notify the user the MR was created. And when the community MR is
merged, it will notify the user who merged it so they don't forget about
merging the upper version MR too.

## Check and report by slack 

Gorrabot checks the status of the projects, and give a summary of: 

 * Staled MR (both WIP and non-WIP) not update in a given amount of time
 * The accepted issues are less than a boundary
 * There is no issue waiting for a decision.
 
And gives each developer a summary of undesirable behaviour. Moreover, it gives
a summary of the team to the REPORT users.

### Staled MR and accepted issues

Based on the default concept of gitlab, this value is obtained by the gitlab 
API.

### Waiting for decision issues

When the `waiting-decision` label is set in a issue, gorrabot will parse its 
description and look for a line starting with the prefix `WFD: `. After that 
prefix, there should be a comma-separated list of gitlab or slack users, whom
decision is expected to resolve the issue. 

In the case of gitlab users, you should reference them with an @, as the common
gitlab behaviour. In the case of slack users, based on slack API, you should 
use the email username. E.g. for `uname@company.com` the id is `uname` not 
User Name, or any other display name.

# Summary of special labels

* `no-changelog`: Use this when the merge request consists of a really
  small check that shouldn't be reflected on the `RELEASE.md` file
  See [this](#changelog-check) for more documentation about this
* `multiple-merge-requests`: The only label that must be applied to issues
  instead of merge requests. Avoid gorrabot changing the status and labels of
  issues labeled with this. See [this](#multiple-merge-requests) for more
  information
* `sacate-la-gorra`: A wildcard label that totally disables gorrabot on
  that merge request. **THIS ISN'T RECOMMENDED, SO THINK TWICE WHEN USING THIS**
* `waiting-decision`: This issue needs a decision be taken before be resolved. 
  See [this](#waiting-for-decision-issues) for more information.


# Design goals

## Avoid state

To simplify deployment and avoid having to do data migrations, it makes sense
to not use a database in this project. Most things can be achieved this way.

For example, lets take the [Branch nomenclature
check](#branch-nomenclature-check) feature. I don't want gorrabot to make a
comment each time the merge request is modified, so I need a way to avoid
duplicating this kind of comment.

The traditional way to solve this would be to store in a database the merge
requests where this comment has already been made. I instead check for the
comments of the MR. If there exists a comment similar to what gorrabot
wants to comment, return without commenting. When done this way, I don't
need to store anything in a database, just use the Gitlab information.

This has some small drawbacks also. For example, if I want to change the text
of the comment to something new and a merge request has already a comment with
the old version text, there will be two similar comments with different text.

I think this behavior is acceptable for what we're doing, and doing big
architecture changes just to fix this kind of things doesn't bring much
benefits. Sacrificing simplicity is bad.

## Don't replace a CI

The goal of this project is to help us with some things related to our
development process, not to our code base itself. For this things,
having a continuous integration seems to be a better choice.
