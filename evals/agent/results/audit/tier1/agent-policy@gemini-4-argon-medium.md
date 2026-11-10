# Audit worksheet: `agent-policy@gemini-4-argon-medium`

Population: 37 `retired` failures, 19 `lost` cases; sample seed 20261106, up to 50 each. Verdict per case: `correct` or `matching error`.

## retired

1. `meme-nofiller/pl_014/update/1#7` (tracking, session 1): stale ['daily journal subscription'] -> current ['dranthazon']
   - `@overlay/user/subscription-daily-journal`: "The user is subscribed to a Daily Journal subscription to keep track of thoughts and daily activities (as of March 2023)." / "- The user is subscribed to a Daily Journal subscription as of March 1, 2023." / "- They use the Daily Journal subscription to help keep track of their thoughts and daily activities."
   - cards stating the current value: @overlay/user/subscription-dranthazon
2. `meme-nofiller/pl_019/update/2#5` (tracking, session 2): stale ['a daily news podcast'] -> current ['thyrelion (anime)']
   - `@overlay/media/news-podcast`: "The user listens to a daily news podcast, particularly enjoying politics and significant global events (as of 2023-03-02)." / "- As of 2023-03-02, the user currently listens to a daily news podcast to keep up with current events."
   - cards stating the current value: @overlay/media/current-media-thyrelion
3. `meme-nofiller/pl_024/update/1#5` (tracking, session 1): stale ['sarah'] -> current ['jessica']
   - `@overlay/hobbies/video-games`: "The user's hobby is playing video games, mostly enjoying action-adventure games, RPGs, and open-world titles, often playing with their partner Sarah."
   - cards stating the current value: @overlay/finance/engagement-ring, @overlay/hobbies/basketball, @overlay/relationships/partner-jessica
4. `meme-nofiller/pl_032/update/4#1` (root, session 4): stale ['in a relationship'] -> current ['married']
   - `@overlay/user/financial-goal`: "- The user notes that being in a relationship adds a different perspective on financial goals when planning for a future big purchase like a house (see [[user/relationship-status]])."
   - cards stating the current value: @overlay/user/partner-name, @overlay/user/relationship-status-married
5. `meme-nofiller/pl_008/update/2#5` (tracking, session 2): stale ['xelvoria'] -> current ['dranthazon']
   - `@overlay/hobbies/cooking`: "- The user watches cooking tutorials and food-related shows on [[subscriptions/xelvoria]] to support their cooking hobby."
   - cards stating the current value: @overlay/hobbies/board-games, @overlay/subscriptions/dranthazon
6. `meme-nofiller/pl_036/update/2#5` (tracking, session 2): stale ['james', 'jordan'] -> current ['taylor']
   - `@overlay/hobbies/drawing-painting`: "- Related: [[relationships/partner-james]], [[preferences/favorite-restaurant]], [[subscriptions/meal-kit]]"
   - `@overlay/hobbies/running-club`: "- They asked for tips on improving their running performance and running with their partner Jordan ([[relationships/partner-jordan]])."
   - cards stating the current value: @overlay/hobbies/wine-tasting-club, @overlay/relationships/partner-taylor
7. `meme-nofiller/pl_028/update/4#1` (root, session 4): stale ['caeltura systems'] -> current ['quenlix group']
   - `@overlay/user/hobbies/basketball`: "- Fitting in basketball practice can be challenging due to their [[user/work/schedule|9-to-5 fixed work hours]] at [[user/work/employer|Caeltura Systems]]."
   - `@overlay/user/projects/data-pipeline-build`: "- The user works at [[user/work/employer|Caeltura Systems]] on a [[user/work/schedule|9-to-5 fixed schedule]]."
   - `@overlay/user/relationships/partner-jessica`: "- Jessica is supportive, which helps the user maintain motivation for both work at [[user/work/employer|Caeltura Systems]] and [[user/hobbies/basketball|basketball]] training."
   - cards stating the current value: @overlay/user/work/employer-quenlix-group
8. `meme-nofiller/sw_011/update/4#1` (root, session 4): stale ['quenthar'] -> current ['veltrion']
   - `@overlay/team/design-system`: "Team Design System: Quenthar Design v1" / "Quenthar Design v1" / "The user's team design system is Quenthar Design v1 (recorded 2023-03-01)."
   - cards stating the current value: @overlay/team/framework-veltrion
9. `meme-nofiller/pl_048/update/1#3` (tracking, session 1): stale ['jessica'] -> current ['alex']
   - `@overlay/hobbies/woodworking`: "- They collaborate on woodworking projects with their partner [[relationships/partner]] (Jessica), making decorative pieces and functional items like shelves."
   - cards stating the current value: @overlay/hobbies/cycling, @overlay/relationships/partner-alex
10. `meme-nofiller/pl_039/update/1#5` (tracking, session 1): stale ['whispers of zarinthea (tv)'] -> current ['a true crime podcast']
   - `@overlay/user/current-media`: "User Current Media: Whispers of Zarinthea (TV)"
   - cards stating the current value: @overlay/user/podcast
11. `meme-nofiller/pl_049/update/2#5` (tracking, session 2): stale ['xelvoria', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/hobbies/guitar`: "- Related resources and events: [[subscriptions/xelvoria]], [[events/upcoming-concert]]."
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
12. `meme-nofiller/pl_049/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['dranthazon']
   - `@overlay/hobbies/guitar`: "- Related resources and events: [[subscriptions/xelvoria]], [[events/upcoming-concert]]."
   - cards stating the current value: @overlay/subscriptions/dranthazon
13. `meme-nofiller/pl_044/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['zorvista premium']
   - `@overlay/user/subscription`: "User Subscription: Xelvoria" / "Xelvoria" / "The user is subscribed to Xelvoria and finds the content really engaging."
   - cards stating the current value: @overlay/user/subscription-zorvista-premium
14. `meme-nofiller/sw_038/update/4#1` (root, session 4): stale ['synthari'] -> current ['dravex']
   - `@overlay/project/dev-server`: "Team Dev Server Command (synthari launch --hmr)" / "synthari launch --hmr" / "synthari"
   - `@overlay/project/package-manager-synthari`: "Team Package Manager (Synthari Modules)" / "Synthari Modules" / "The team's package manager is Synthari Modules (replacing Veltrion Pkg and Pyronis Bundle)."
   - cards stating the current value: @overlay/project/framework-dravex
15. `meme-nofiller/pl_022/update/1#5` (tracking, session 1): stale ['james'] -> current ['alex']
   - `@overlay/hobbies/woodworking`: "- Their partner [[profile/partner]] (James) is quite supportive of their woodworking projects."
   - cards stating the current value: @overlay/hobbies/tennis, @overlay/profile/partner-alex
16. `meme-nofiller/pl_048/update/2#5` (tracking, session 2): stale ['jessica', 'alex'] -> current ['chris']
   - `@overlay/hobbies/woodworking`: "- They collaborate on woodworking projects with their partner [[relationships/partner]] (Jessica), making decorative pieces and functional items like shelves."
   - cards stating the current value: @overlay/hobbies/cycling, @overlay/relationships/partner-chris
17. `meme-nofiller/pl_014/update/2#5` (tracking, session 2): stale ['daily journal subscription', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/user/subscription-daily-journal`: "The user is subscribed to a Daily Journal subscription to keep track of thoughts and daily activities (as of March 2023)." / "- The user is subscribed to a Daily Journal subscription as of March 1, 2023." / "- They use the Daily Journal subscription to help keep track of their thoughts and daily activities."
   - cards stating the current value: @overlay/user/subscription-pyrethon-plus
18. `meme-nofiller/sw_034/update/4#1` (root, session 4): stale ['veltrion'] -> current ['synthari']
   - `@overlay/project/design-system`: "Team Design System: Veltrion UI Kit v2" / "Veltrion UI Kit" / "Veltrion UI Kit v2"
   - cards stating the current value: @overlay/project/framework-synthari
19. `meme-nofiller/pl_024/update/2#5` (tracking, session 2): stale ['sarah', 'jessica'] -> current ['taylor']
   - `@overlay/hobbies/basketball`: "The user plays pickup basketball games with friends at local courts (not in a league) and enjoys hiking outdoors with their partner Jessica." / "- The user and their partner Jessica ([[relationships/partner-jessica]]) also both enjoy going out for hikes together outdoors."
   - `@overlay/hobbies/video-games`: "The user's hobby is playing video games, mostly enjoying action-adventure games, RPGs, and open-world titles, often playing with their partner Sarah."
   - cards stating the current value: @overlay/hobbies/hiking, @overlay/relationships/partner-taylor
20. `meme-nofiller/pl_043/update/2#5` (tracking, session 2): stale ['xelvoria', 'thyranote'] -> current ['zorvista premium']
   - `@overlay/hobbies/rock-climbing`: "- The user tracks their climbing goals and progress using [[subscriptions/thyranote]]."
   - cards stating the current value: @overlay/subscriptions/zorvista-premium
21. `meme-nofiller/pl_025/update/2#5` (tracking, session 2): stale ['xelvoria'] -> current ['pyrethon plus']
   - `@overlay/hobbies/woodworking`: "- Related resource: [[subscriptions/xelvoria]]."
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
22. `meme-nofiller/pl_043/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['thyranote']
   - `@overlay/subscriptions/xelvoria`: "User's Subscription: Xelvoria" / "Xelvoria" / "The user is subscribed to Xelvoria, a platform for discovering new content (as of 2023-03-01)."
   - cards stating the current value: @overlay/hobbies/rock-climbing, @overlay/subscriptions/thyranote
23. `meme-nofiller/pl_042/update/4#1` (root, session 4): stale ['pre-diabetes'] -> current ['high blood pressure']
   - `@overlay/health/dietary-restriction-no-processed-food`: "- Related health condition: [[health/pre-diabetes]]."
   - `@overlay/sports/running-club`: "- Related fitness and health cards: [[sports/volleyball]] and [[health/pre-diabetes]]."
   - cards stating the current value: @overlay/health/high-blood-pressure
24. `meme-nofiller/pl_028/update/2#5` (tracking, session 2): stale ['zorvista premium', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/user/hobbies/basketball`: "- They use [[user/subscriptions/dranthazon|Dranthazon]] for basketball training content and shooting techniques."
   - cards stating the current value: @overlay/user/projects/data-pipeline-build, @overlay/user/subscriptions/pyrethon-plus
25. `meme-nofiller/pl_048/update/4#1` (root, session 4): stale ['pre-diabetes'] -> current ['herniated disc']
   - `@overlay/hobbies/cycling`: "The user is part of a cycling club that goes for rides on the weekends, cycles with friends or family and partner Chris, and uses cycling to stay active and manage pre-diabetes." / "- The user plays cycling (first recorded on 2023-03-01) and uses it to stay active and help manage their [[health/pre-diabetes]]."
   - cards stating the current value: @overlay/health/herniated-disc
26. `meme-nofiller/pl_032/update/1#5` (tracking, session 1): stale ['thyranote'] -> current ['zorvista premium']
   - `@overlay/user/subscription`: "Subscription: Thyranote (Reading & Notes Tracker)" / "Thyranote" / "The user is subscribed to Thyranote for keeping track of their reading and notes (as of 2023-03-01)."
   - cards stating the current value: @overlay/user/streaming-subscription, @overlay/user/tv-show
27. `meme-nofiller/pl_047/update/4#1` (root, session 4): stale ['zypherix labs'] -> current ['dranthex logistics']
   - `@overlay/work/ux-research`: "- See also [[work/employer]] for their employer (Zypherix Labs)."
   - cards stating the current value: @overlay/work/commute-duration-1-5-hours, @overlay/work/employer-dranthex-logistics, @overlay/work/job-title-product-manager, @overlay/work/office-location-quivira-springs
28. `meme-nofiller/sw_001/update/4#1` (root, session 4): stale ['synthari'] -> current ['veltrion']
   - `@overlay/project/dev-server`: "Dev Server Command: synthari launch --hmr" / "synthari launch" / "To run the dev server with hot module replacement, use `synthari launch --hmr`."
   - cards stating the current value: @overlay/project/framework-veltrion, @overlay/project/incident-runbook, @overlay/project/package-manager, @overlay/project/secret-manager
29. `meme-nofiller/pl_009/update/4#1` (root, session 4): stale ['tendinitis'] -> current ['chronic migraine']
   - `@overlay/user/activity-running-club`: "- The user asked for tips on improving running performance while managing [[user/health-condition-tendinitis]]."
   - `@overlay/user/subscription-xelvoria`: "The user is subscribed to Xelvoria for health and fitness insights to manage running and tendinitis." / "- Xelvoria provides health and wellness content, insights, and strategies that help the user manage their health and fitness, specifically their [[user/activity-running-club]] running and [[user/health-condition-tendinitis]] tendinitis issues."
   - cards stating the current value: @overlay/user/dietary-restriction-no-alcohol, @overlay/user/exercise-routine-yoga, @overlay/user/health-condition-chronic-migraine
30. `meme-nofiller/pl_022/update/2#3` (tracking, session 2): stale ['james', 'alex'] -> current ['taylor']
   - `@overlay/hobbies/tennis`: "- The user asked whether practicing with their partner [[profile/partner-alex]] (Alex) can help improve their tennis skills."
   - `@overlay/hobbies/woodworking`: "- Their partner [[profile/partner]] (James) is quite supportive of their woodworking projects."
   - cards stating the current value: @overlay/hobbies/wine-tasting-club, @overlay/profile/partner-taylor
31. `meme-nofiller/pl_039/update/2#5` (tracking, session 2): stale ['whispers of zarinthea (tv)', 'a true crime podcast'] -> current ['xelvari dawn (book)']
   - `@overlay/user/podcast`: "User currently listens to a true crime podcast and finds the investigative aspects and twists compelling." / "- User currently listens to a true crime podcast (as of 2023/03/02)."
   - cards stating the current value: @overlay/user/current-media-xelvari-dawn
32. `meme-nofiller/pl_034/update/2#3` (tracking, session 2): stale ['xelvoria', 'thyranote'] -> current ['zorvista premium']
   - `@overlay/hobbies/woodworking`: "- They subscribe to Xelvoria for woodworking resources ([[subscriptions/xelvoria]])."
   - cards stating the current value: @overlay/subscriptions/zorvista-premium
33. `meme-nofiller/pl_034/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['thyranote']
   - `@overlay/hobbies/woodworking`: "- They subscribe to Xelvoria for woodworking resources ([[subscriptions/xelvoria]])."
   - `@overlay/subscriptions/xelvoria`: "Subscription: Xelvoria Woodworking Platform" / "Xelvoria subscription" / "Subscribed to Xelvoria, a platform offering woodworking resources (as of March 2023)."
   - cards stating the current value: @overlay/subscriptions/thyranote
34. `meme-nofiller/pl_036/update/1#7` (tracking, session 1): stale ['james'] -> current ['jordan']
   - `@overlay/hobbies/drawing-painting`: "- Related: [[relationships/partner-james]], [[preferences/favorite-restaurant]], [[subscriptions/meal-kit]]"
   - cards stating the current value: @overlay/hobbies/running-club, @overlay/relationships/partner-jordan
35. `meme-nofiller/pl_035/update/2#5` (tracking, session 2): stale ['zorvista premium'] -> current ['pyrethon plus']
   - `@overlay/media/watching`: "- Related streaming service: [[subscriptions/streaming]] (Zorvista Premium)."
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
36. `meme-nofiller/pl_032/update/2#5` (tracking, session 2): stale ['thyranote', 'zorvista premium'] -> current ['meal kit (kelvimeal)']
   - `@overlay/user/meal-kit-subscription`: "Zorvista Premium" / "Thyranote" / "The user switched subscriptions again and is currently subscribed to the Kelvimeal meal kit service (as of 2023-03-04), replacing Zorvista Premium and Thyranote."
   - cards stating the current value: none
37. `meme-nofiller/pl_012/update/4#1` (root, session 4): stale ['dating'] -> current ['married']
   - `@overlay/user/volunteer-community-service`: "- They use their vehicle ([[user/vehicle-vorantel-suv]]) and have a supportive partner ([[user/partner-mike]], [[user/relationship-status-dating]]) while doing volunteer work."
   - cards stating the current value: @overlay/user/relationship-status-married

## lost

1. `meme-nofiller/pl_016/3#1` (point 3, dependent, travel_plan): value "cross-country road trip (2 weeks)"
   - `@overlay/user/travel-plan-cross-country-road-trip`: "User Travel Plan: 2-Week Cross-Country Road Trip (or 1-Week Zynthera Bay Beach Trip if Relationship Changes)" / "cross-country road trip"
   - `@overlay/user/vehicle-vorantel-suv`: "The user drives a Vorantel SUV (as of 2023-03-03), chosen for its reliability for both city driving and off-road adventures." / "- The user notes that the Vorantel SUV is supposed to be pretty reliable for both city driving and off-road adventures."
2. `meme-nofiller/pl_025/0#11` (point end, plain, partner): value "jessica"
   - no active card shares a distinctive word
3. `meme-nofiller/pl_032/2#5` (point end, plain, subscription_service): value "meal kit (kelvimeal)"
   - `@overlay/user/meal-kit-subscription`: "Current Subscription: Kelvimeal (Meal Kit Service)" / "Kelvimeal"
   - `@overlay/user/streaming-subscription (inactive)`: "[INACTIVE] Streaming Subscription: Zorvista Premium" / "streaming subscription"
   - `@overlay/user/subscription (inactive)`: "[INACTIVE] Subscription: Thyranote (Reading & Notes Tracker)" / "reading subscription"
   - `@overlay/user/hobby`: "- Related subscription: [[user/subscription]]."
   - `@overlay/user/tv-show`: "- Related streaming subscription: [[user/streaming-subscription]] (Zorvista Premium)."
4. `meme-nofiller/pl_047/1#1` (point end, plain, sports): value "basketball"
   - no active card shares a distinctive word
5. `meme-nofiller/pl_010/0#5` (point 3, plain, social_gathering): value "brunch with college friends monthly"
   - `@overlay/social/regular-meetup`: "Regular Social Meetup: Monthly Brunch with College Friends" / "social meetup"
   - `@overlay/finances/financial-goal-credit-card-debt`: "The user's financial goal is paying off credit card debt via consistent monthly payments and cutting back on unnecessary expenses (as of 2023-03-03)." / "- The user has also tried to cut back on unnecessary expenses to free up more money for their monthly debt payments."
   - `@overlay/social/board-game-group`: "- Related social and gaming cards: [[social/regular-meetup]] and [[hobbies/video-games]]."
   - `@overlay/social/thanksgiving-gathering`: "Upcoming Event: Thanksgiving Gathering Planning" / "Thanksgiving gathering"
6. `meme-nofiller/sw_006/3#5` (point 3, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/team/error-log-vorathis-query-planner`: "Exact Error Log: SegmentationFault in vorathis_query_planner.so (commit 7a4f9e2)" / "error log"
   - `@overlay/team/incident-runbook`: "Incident Runbook: wiki.aurora.dev/incident-response" / "wiki.aurora.dev/incident-response"
   - `@overlay/team/production-alerts-channel`: "Production Alerts Channel: #aurora-alerts" / "#aurora-alerts"
   - `@overlay/team/team-channel`: "Team Channel: #aurora-dev" / "#aurora-dev"
7. `meme-nofiller/pl_038/0#11` (point 3, plain, planned_purchase): value "electric car"
   - `@overlay/plans/electric-car-purchase (inactive)`: "[INACTIVE] Planned Big Purchase: Electric Car" / "planned big purchase"
   - `@overlay/vehicles/quorvel-ev (inactive)`: "current car" / "electric vehicle"
   - `@overlay/vehicles/vorantel-suv`: "current car" / "what car does user drive"
   - `@overlay/plans/cross-country-road-trip`: "Planned Trip: Cross-Country Road Trip (2 Weeks)"
   - `@overlay/vehicles/current-car (inactive)`: "current car" / "what car does user drive"
8. `meme-nofiller/pl_038/0#11` (point end, plain, planned_purchase): value "electric car"
   - `@overlay/plans/electric-car-purchase (inactive)`: "[INACTIVE] Planned Big Purchase: Electric Car" / "planned big purchase"
   - `@overlay/vehicles/quorvel-ev (inactive)`: "current car" / "electric vehicle"
   - `@overlay/vehicles/vorantel-suv`: "current car" / "what car does user drive"
   - `@overlay/plans/cross-country-road-trip`: "Planned Trip: Cross-Country Road Trip (2 Weeks)"
   - `@overlay/vehicles/current-car (inactive)`: "current car" / "what car does user drive"
9. `meme-nofiller/sw_039/3#13` (point end, plain, error_log): value "panicexception: thread 'tokio-runtime-worker' panicked at 'index out of bounds: the len is 0 but the index is 5', src/handlers/auth.rs:142:23. stack trace shows recursive call in middleware_chain to request_validator to token_parser. restart triggered automatic failover at 2024-04-02t14:18:33z"
   - `@overlay/team/error-log-auth-panic`: "Exact Error Log: PanicException in src/handlers/auth.rs:142:23" / "exact error log"
   - `@overlay/team/deployment-target-korinth-hosting`: "- [[team/log-drain]] (`logs.korinth.dev/aurora`) and [[team/docker-image]] (`orinthal-registry/aurora:deploy`, along with [[team/dockerfile]] at `infra/orinthal/Dockerfile`) were also determined by deploying on Thandrel Infra."
   - `@overlay/team/log-drain`: "Team Log Drain: logs.korinth.dev/aurora" / "log drain"
   - `@overlay/team/on-call-rotation`: "Team On-Call Rotation: Volunteer-Based with Weekly Signup" / "on-call rotation"
   - `@overlay/team/production-alerts`: "- `#aurora-oncall-alerts` is the dedicated channel for production alerts, distinct from the general team communication channel `#aurora-dev` ([[team/channel]]) and related to the team's on-call operations ([[team/on-call-rotation]])."
10. `meme-nofiller/sw_034/3#9` (point end, plain, error_log): value "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status = 'shipped' where region = 'us-east'. query 2 was delete from orders where created_at < now() - interval '30 days'. first seen at 2024-08-04t22:33:18z; recommend serializable isolation review"
   - `@overlay/project/deadlock-error-log-aurora-orders`: "Exact Error Log: DeadlockDetected on aurora_orders (Transactions 4821 and 4823)" / "deadlock error log"
   - `@overlay/project/code-review-policy`: "Team Code Review Policy: 2 Approvals + Security Review for auth/ Directory" / "code review policy"
   - `@overlay/project/documentation-repo`: "Project docs are located at github.com/aurora-team/docs." / "- Project docs are located at `github.com/aurora-team/docs` (recorded 2023/03/02)."
   - `@overlay/project/production-alerts-channel`: "- Production alerts and incidents are sent to the `#zenith-incidents` channel."
   - `@overlay/project/framework-synthari`: "- Note on dependent tools: Because the team switched frameworks from Veltrion to Synthari, the build tool ([[project/build-tool]]) changes from Pyronis Build to Dranith Compiler, the build command ([[project/build-command]]) changes from `pyronis pack --quick` to `dranith compile --emit bundle`, and"
11. `meme-nofiller/sw_034/3#9` (point 3, plain, error_log): value "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status = 'shipped' where region = 'us-east'. query 2 was delete from orders where created_at < now() - interval '30 days'. first seen at 2024-08-04t22:33:18z; recommend serializable isolation review"
   - `@overlay/project/deadlock-error-log-aurora-orders`: "Exact Error Log: DeadlockDetected on aurora_orders (Transactions 4821 and 4823)" / "deadlock error log"
   - `@overlay/project/code-review-policy`: "Team Code Review Policy: 2 Approvals + Security Review for auth/ Directory" / "code review policy"
   - `@overlay/project/database-backups`: "- The 12-hour interval and 7-day retention policy ensure the team has regular recovery points without taking up too much storage space."
   - `@overlay/project/documentation-repo`: "Project docs are located at github.com/aurora-team/docs." / "- Project docs are located at `github.com/aurora-team/docs` (recorded 2023/03/02)."
   - `@overlay/project/production-alerts-channel`: "- Production alerts and incidents are sent to the `#zenith-incidents` channel."
12. `meme-nofiller/sw_044/0#5` (point end, plain, project_structure): value "workspace with /services and /common"
   - `@overlay/project/workspace-structure`: "Project Workspace Structure: /services and /common" / "workspace structure"
   - `@overlay/project/design-system`: "- Related project tooling: [[project/package-manager]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]]."
   - `@overlay/project/framework (inactive)`: "- Related project architecture and tooling: [[project/workspace-structure]], [[project/design-system]], [[project/package-manager-synthari-modules]], [[project/dev-server-command]]."
   - `@overlay/project/framework-korvel`: "- Related project architecture and tooling: [[project/workspace-structure]], [[project/design-system]], [[project/package-manager-synthari-modules]], [[project/dev-server-command]], [[project/test-framework]], [[project/build-tool]]."
   - `@overlay/project/package-manager (inactive)`: "The team's package manager is Pyronis Bundle, used for dependency management across the project." / "- Pyronis Bundle is used to streamline dependency management across the project."
   - `@overlay/project/package-manager-quorix-hub (inactive)`: "- The team switched to Quorix Hub recently to streamline dependency management across the project." / "- Related project tooling and setup: [[project/design-system]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]], [[project/test-coverage-target]], [[project/dev-server-command]], [[project/changelog]]."
   - `@overlay/project/package-manager-synthari-modules`: "- Related project tooling and setup: [[project/code-review-policy]], [[project/framework]], [[project/default-branch]], [[project/design-system]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]], [[project/test-coverage-target]], [[project/dev-server-comma"
   - `@overlay/project/secret-manager`: "- Related project cards: [[project/design-system]], [[project/package-manager]], [[project/workspace-structure]], [[project/escalation-contact]]."
   - `@overlay/project/test-coverage-target`: "- Related project standards and tooling: [[project/package-manager-quorix-hub]], [[project/dev-server-command]], [[project/changelog]], [[project/workspace-structure]]."
   - `@overlay/project/build-command`: "- This command is determined by the fact that the team uses Zelthra Pack as their build tool (see [[project/build-tool]]), which in turn depends on using the Dravex framework (see [[project/framework]])." / "- Related commands: [[project/dev-server-command]], [[project/test-command]]."
13. `meme-nofiller/sw_039/3#13` (point 3, plain, error_log): value "panicexception: thread 'tokio-runtime-worker' panicked at 'index out of bounds: the len is 0 but the index is 5', src/handlers/auth.rs:142:23. stack trace shows recursive call in middleware_chain to request_validator to token_parser. restart triggered automatic failover at 2024-04-02t14:18:33z"
   - `@overlay/team/error-log-auth-panic`: "Exact Error Log: PanicException in src/handlers/auth.rs:142:23" / "exact error log"
   - `@overlay/team/authentication-method`: "auth method"
   - `@overlay/team/log-drain`: "Team Log Drain: logs.korinth.dev/aurora" / "log drain"
   - `@overlay/team/on-call-rotation`: "Team On-Call Rotation: Volunteer-Based with Weekly Signup" / "on-call rotation"
14. `meme-nofiller/sw_044/0#5` (point 3, plain, project_structure): value "workspace with /services and /common"
   - `@overlay/project/workspace-structure`: "Project Workspace Structure: /services and /common" / "workspace structure"
   - `@overlay/project/design-system`: "- Related project tooling: [[project/package-manager]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]]."
   - `@overlay/project/escalation-contact`: "- Related project cards: [[project/design-system]], [[project/package-manager]], [[project/workspace-structure]], [[project/secret-manager]]."
   - `@overlay/project/framework`: "- Related project architecture and tooling: [[project/workspace-structure]], [[project/design-system]], [[project/package-manager-synthari-modules]], [[project/dev-server-command]]."
   - `@overlay/project/package-manager (inactive)`: "The team's package manager is Pyronis Bundle, used for dependency management across the project." / "- Pyronis Bundle is used to streamline dependency management across the project."
   - `@overlay/project/package-manager-quorix-hub (inactive)`: "- The team switched to Quorix Hub recently to streamline dependency management across the project." / "- Related project tooling and setup: [[project/design-system]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]], [[project/test-coverage-target]], [[project/dev-server-command]], [[project/changelog]]."
   - `@overlay/project/package-manager-synthari-modules`: "- Related project tooling and setup: [[project/code-review-policy]], [[project/framework]], [[project/default-branch]], [[project/design-system]], [[project/workspace-structure]], [[project/escalation-contact]], [[project/secret-manager]], [[project/test-coverage-target]], [[project/dev-server-comma"
   - `@overlay/project/secret-manager`: "- Related project cards: [[project/design-system]], [[project/package-manager]], [[project/workspace-structure]], [[project/escalation-contact]]."
   - `@overlay/project/test-coverage-target`: "- Related project standards and tooling: [[project/package-manager-quorix-hub]], [[project/dev-server-command]], [[project/changelog]], [[project/workspace-structure]]."
   - `@overlay/project/build-command`: "- This command is determined by the fact that the team uses Zelthra Pack as their build tool (see [[project/build-tool]]), which in turn depends on using the Dravex framework (see [[project/framework]])." / "- Related commands: [[project/dev-server-command]], [[project/test-command]]."
15. `meme-nofiller/sw_034/2#5` (point 3, plain, project_structure): value "workspace with /services and /common"
   - `@overlay/project/workspace-structure`: "Project Workspace Structure: /services and /common" / "workspace structure"
   - `@overlay/project/build-command`: "- Using `pyronis pack --quick` is determined by the fact that the team uses Pyronis Build ([[project/build-tool]]); if the build tool changes, the build command will change." / "- Conditional rule: If the team changes the build tool (e.g., to Dranith Compiler when switching away from [[project/framework]] Veltrion), the build command will be `dranith compile --emit bundle`."
   - `@overlay/project/build-tool`: "project build tool" / "- Using Pyronis Build is determined by which framework the team uses (currently [[project/framework]], Veltrion); if the team switches frameworks, the build tool will change."
   - `@overlay/project/design-system`: "- Related framework: [[project/framework]] (Veltrion)."
   - `@overlay/project/documentation-repo`: "Project Documentation: github.com/aurora-team/docs" / "project docs"
   - `@overlay/project/framework`: "- The team uses Veltrion as their framework alongside their design system [[project/design-system]] (Veltrion UI Kit v2)."
   - `@overlay/project/onboarding-guide`: "- The onboarding guide at `github.com/aurora-team/onboarding` helps new team members get integrated smoothly into the project alongside the general project documentation at [[project/documentation-repo]] (`github.com/aurora-team/docs`)."
   - `@overlay/project/test-command`: "- Using `tarvex verify --all` is determined by the fact that the team uses Tarvex Verify ([[project/test-tool]], which is determined by [[project/framework]] Veltrion); if the testing tool changes, the test command would change."
   - `@overlay/project/test-tool`: "- Using Tarvex Verify is determined by which framework the team uses (currently [[project/framework]], Veltrion); if the team switches frameworks, the testing tool would change." / "- The testing tool choice directly determines the team's test command ([[project/test-command]])."
16. `meme-nofiller/sw_006/3#5` (point end, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/team/error-log-vorathis-query-planner`: "Exact Error Log: SegmentationFault in vorathis_query_planner.so (commit 7a4f9e2)" / "error log"
   - `@overlay/team/incident-runbook`: "Incident Runbook: wiki.aurora.dev/incident-response" / "wiki.aurora.dev/incident-response"
   - `@overlay/team/onboarding-guide`: "Onboarding Guide: notion.so/aurora-team/new-hire" / "notion.so/aurora-team/new-hire"
   - `@overlay/team/team-channel`: "Team Channel: #aurora-dev" / "#aurora-dev"
17. `meme-nofiller/pl_032/2#5` (point 3, plain, subscription_service): value "meal kit (kelvimeal)"
   - `@overlay/user/meal-kit-subscription`: "Current Subscription: Kelvimeal (Meal Kit Service)" / "Kelvimeal"
   - `@overlay/user/streaming-subscription (inactive)`: "[INACTIVE] Streaming Subscription: Zorvista Premium" / "streaming subscription"
   - `@overlay/user/subscription (inactive)`: "[INACTIVE] Subscription: Thyranote (Reading & Notes Tracker)" / "reading subscription"
   - `@overlay/user/hobby`: "- Related subscription: [[user/subscription]]."
   - `@overlay/user/tv-show`: "- Related streaming subscription: [[user/streaming-subscription]] (Zorvista Premium)."
18. `meme-nofiller/sw_002/4#7` (point end, plain, meeting_day): value "every thursday 2pm"
   - `@overlay/project/team-meeting`: "Team Meeting: Every Thursday at 2pm" / "team meeting"
19. `meme-nofiller/sw_034/2#5` (point end, plain, project_structure): value "workspace with /services and /common"
   - `@overlay/project/workspace-structure`: "Project Workspace Structure: /services and /common" / "workspace structure"
   - `@overlay/project/build-command`: "- Using `pyronis pack --quick` is determined by the fact that the team uses Pyronis Build ([[project/build-tool]]); if the build tool changes, the build command will change." / "- Conditional rule: If the team changes the build tool (e.g., to Dranith Compiler when switching away from [[project/framework]] Veltrion), the build command will be `dranith compile --emit bundle`."
   - `@overlay/project/build-tool`: "project build tool" / "- Using Pyronis Build is determined by which framework the team uses (currently [[project/framework]], Veltrion); if the team switches frameworks, the build tool will change."
   - `@overlay/project/changelog-location`: "Project Changelog Location: GitHub Releases Page" / "project changelog"
   - `@overlay/project/design-system`: "- Related framework: [[project/framework]] (Veltrion)."
   - `@overlay/project/documentation-repo`: "Project Documentation: github.com/aurora-team/docs" / "project docs"
   - `@overlay/project/framework (inactive)`: "- The team uses Veltrion as their framework alongside their design system [[project/design-system]] (Veltrion UI Kit v2)."
   - `@overlay/project/framework-synthari`: "- Note on dependent tools: Because the team switched frameworks from Veltrion to Synthari, the build tool ([[project/build-tool]]) changes from Pyronis Build to Dranith Compiler, the build command ([[project/build-command]]) changes from `pyronis pack --quick` to `dranith compile --emit bundle`, and"
   - `@overlay/project/on-call-rotation`: "- Related incident alerting: production alerts go to [[project/production-alerts-channel]] (#zenith-incidents)."
   - `@overlay/project/onboarding-guide`: "- The onboarding guide at `github.com/aurora-team/onboarding` helps new team members get integrated smoothly into the project alongside the general project documentation at [[project/documentation-repo]] (`github.com/aurora-team/docs`)."

