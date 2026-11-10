# Audit worksheet: `agent-policy@gemini-3.8-flash-medium`

Population: 63 `retired` failures, 222 `lost` cases; sample seed 20261106, up to 50 each. Verdict per case: `correct` or `matching error`.

## retired

1. `meme-nofiller/pl_044/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['zorvista premium']
   - `@overlay/subscriptions/xelvoria`: "Xelvoria Subscription" / "Xelvoria" / "Xelvoria subscription"
   - cards stating the current value: @overlay/subscriptions/zorvista-premium
2. `meme-nofiller/pl_011/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['daily journal subscription']
   - `@overlay/user/subscriptions/xelvoria`: "User Subscription: Xelvoria Platform" / "Xelvoria subscription" / "Xelvoria platform"
   - cards stating the current value: @overlay/user/subscriptions/daily-journal
3. `meme-nofiller/pl_012/update/2#5` (tracking, session 2): stale ['zyvanta sedan', 'dranthis pickup'] -> current ['vorantel suv']
   - `@overlay/hobbies/rock-climbing`: "The user practices rock climbing several times a week, utilizing a nearby climbing gym and driving a Dranthis Pickup to outdoor spots." / "- User drives a Dranthis Pickup ([[vehicles/dranthis-pickup]]) to haul gear and reach climbing locations."
   - cards stating the current value: @overlay/vehicles/vorantel-suv
4. `meme-nofiller/pl_019/update/2#5` (tracking, session 2): stale ['a daily news podcast'] -> current ['thyrelion (anime)']
   - `@overlay/media/podcasts/daily-news`: "User listens to a daily news podcast as of March 2023, focusing on politics and significant global events." / "- As of March 2, 2023, the user listens to a daily news podcast to keep up with current events."
   - cards stating the current value: none
5. `meme-nofiller/pl_025/update/2#5` (tracking, session 2): stale ['xelvoria'] -> current ['pyrethon plus']
   - `@overlay/hobbies/woodworking`: "- The user learns new woodworking techniques and project ideas through [[subscriptions/xelvoria]]."
   - `@overlay/subscriptions/xelvoria`: "Xelvoria Subscription for Woodworking" / "Xelvoria" / "Xelvoria woodworking"
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
6. `meme-nofiller/pl_006/update/4#1` (root, session 4): stale ['pre-diabetes'] -> current ['anxiety disorder']
   - `@overlay/health/exercise-routine-cycling`: "The user's exercise routine is cycling on weekends, triggered by the health condition change (pre-diabetes resolved) as of March 2023." / "- This routine was triggered by the contingency rule: if health condition changed from [[@overlay/health/pre-diabetes]], exercise routine switches to cycling on weekends." / "- On March 4, 2023, pre-diabetes was treated and resolved (see [[@overlay/health/anxiety-disorder]]), triggering this change in routine."
   - `@overlay/health/regular-appointment-physical-therapy`: "- This appointment was triggered by the contingency rule: if health condition changed from [[@overlay/health/pre-diabetes]], regular appointment switches to physical therapy (2x/week)." / "- On March 4, 2023, pre-diabetes was treated and resolved (see [[@overlay/health/anxiety-disorder]]), triggering the change in regular appointments."
   - cards stating the current value: @overlay/health/anxiety-disorder
7. `meme-nofiller/pl_043/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['thyranote']
   - `@overlay/subscriptions/xelvoria`: "Subscription: Xelvoria Content Platform" / "Xelvoria subscription" / "Xelvoria platform"
   - cards stating the current value: @overlay/subscriptions/thyranote
8. `meme-nofiller/sw_011/update/4#1` (root, session 4): stale ['quenthar'] -> current ['veltrion']
   - `@overlay/project/design-system`: "Team Design System: Quenthar Design v1" / "Quenthar Design" / "Quenthar Design v1"
   - cards stating the current value: @overlay/project/framework-veltrion
9. `meme-nofiller/pl_031/update/4#1` (root, session 4): stale ['seasonal allergies'] -> current ['anxiety disorder']
   - `@overlay/health/medication-quelmithin`: "- Related health condition: user also mentioned having seasonal allergies in [[health/seasonal-allergies]]."
   - cards stating the current value: @overlay/health/anxiety-disorder, @overlay/health/seasonal-allergies-resolved
10. `meme-nofiller/pl_034/update/2#3` (tracking, session 2): stale ['xelvoria', 'thyranote'] -> current ['zorvista premium']
   - `@overlay/hobbies/woodworking`: "- Related platform subscription: [[subscriptions/xelvoria]]."
   - `@overlay/subscriptions/thyranote`: "Thyranote subscription for organization and task management" / "Thyranote subscription" / "Thyranote app"
   - `@overlay/subscriptions/xelvoria`: "Xelvoria subscription for woodworking" / "Xelvoria subscription" / "Xelvoria woodworking"
   - cards stating the current value: @overlay/subscriptions/zorvista-premium
11. `meme-nofiller/pl_027/update/1#5` (tracking, session 1): stale ['xelvoria'] -> current ['thyranote']
   - `@overlay/user/subscriptions/xelvoria`: "Xelvoria Media Subscription" / "Xelvoria" / "Xelvoria subscription"
   - cards stating the current value: @overlay/user/subscriptions/thyranote
12. `meme-nofiller/pl_044/update/4#1` (root, session 4): stale ['high blood pressure'] -> current ['herniated disc']
   - `@overlay/health/high-blood-pressure-resolved`: "High Blood Pressure Treated and Resolved" / "high blood pressure resolved" / "User's high blood pressure has been treated and resolved as of March 2023."
   - cards stating the current value: @overlay/health/herniated-disc, @overlay/health/sleep-schedule-1am-9am, @overlay/health/yoga-exercise-routine
13. `meme-nofiller/sw_021/update/4#1` (root, session 4): stale ['alex kim'] -> current ['seokjin kang']
   - `@overlay/team/approval-authority`: "- Related leadership and review governance include team lead Alex Kim [[team/team-lead]] and core code review policy [[code-reviews/policy]]."
   - cards stating the current value: @overlay/team/seokjin-kang
14. `meme-nofiller/sw_043/update/4#1` (root, session 4): stale ['crysthene db'] -> current ['thalnex store']
   - `@overlay/tech/deadlock-error-log`: "- Error type: `DeadlockDetected` on table `aurora_orders` in the [[tech/database|Crysthene DB]] database."
   - cards stating the current value: @overlay/tech/database-thalnex-store
15. `meme-nofiller/pl_008/update/2#5` (tracking, session 2): stale ['xelvoria'] -> current ['dranthazon']
   - `@overlay/hobbies/cooking`: "- Uses expert cooking tutorials and food shows on [[subscriptions/xelvoria]] to develop new cooking techniques."
   - `@overlay/subscriptions/xelvoria`: "Xelvoria Platform Subscription" / "Xelvoria subscription" / "Xelvoria platform"
   - cards stating the current value: @overlay/subscriptions/dranthazon
16. `meme-nofiller/pl_014/update/2#5` (tracking, session 2): stale ['daily journal subscription', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/habits/journaling`: "Daily Journal Subscription and Routine"
   - `@overlay/subscriptions/dranthazon`: "Dranthazon Content Subscription" / "Dranthazon" / "Dranthazon subscription"
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
17. `meme-nofiller/pl_024/update/1#5` (tracking, session 1): stale ['sarah'] -> current ['jessica']
   - `@overlay/hobbies/video-games`: "The user plays video games as a major hobby, favoring action-adventure and RPG open-world games, and often plays together with partner Sarah." / "- Frequently plays video games together with partner [[relationships/partner-sarah|Sarah]], finding shared gaming especially enjoyable."
   - cards stating the current value: @overlay/finance/engagement-ring, @overlay/hobbies/hiking, @overlay/relationships/partner-jessica
18. `meme-nofiller/sw_001/update/4#1` (root, session 4): stale ['synthari'] -> current ['veltrion']
   - `@overlay/development/dev-server`: "synthari launch" / "synthari hmr" / "Run the local development server using 'synthari launch --hmr' for hot module replacement."
   - cards stating the current value: @overlay/development/veltrion-framework
19. `meme-nofiller/sw_034/update/4#1` (root, session 4): stale ['veltrion'] -> current ['synthari']
   - `@overlay/tech-stack/design-system`: "Veltrion UI Kit v2 Design System" / "Veltrion UI Kit" / "Veltrion UI Kit v2"
   - cards stating the current value: @overlay/tech-stack/synthari-framework
20. `meme-nofiller/pl_022/update/1#5` (tracking, session 1): stale ['james'] -> current ['alex']
   - `@overlay/hobbies/woodworking`: "- The user's partner [[personal/partner|James]] is very supportive of their woodworking endeavors."
   - `@overlay/personal/partner`: "Partner James" / "partner James" / "James"
   - cards stating the current value: @overlay/hobbies/tennis
21. `meme-nofiller/pl_028/update/2#5` (tracking, session 2): stale ['zorvista premium', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/hobbies/basketball`: "- The user uses [[subscriptions/dranthazon]] for basketball training content and shooting techniques (noted 2023/03/03)."
   - `@overlay/subscriptions/dranthazon`: "User Subscription: Dranthazon Basketball Training" / "Dranthazon" / "Dranthazon subscription"
   - `@overlay/subscriptions/zorvista-premium`: "User Subscription: Zorvista Premium" / "Zorvista Premium" / "The user subscribes to Zorvista Premium, enjoying its features and catalog of shows and content."
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
22. `meme-nofiller/pl_041/update/4#1` (root, session 4): stale ['seasonal allergies'] -> current ['lactose intolerance']
   - `@overlay/health/dyntheral-medication`: "- Previously took Korathril for seasonal allergies, with an established condition that changing health conditions would switch medication to Dyntheral."
   - `@overlay/health/exercise-routine`: "- Previously determined by seasonal allergies, with an established condition that the routine remains yoga 2x/week if the health condition changes."
   - cards stating the current value: @overlay/health/lactose-intolerance
23. `meme-nofiller/pl_045/update/2#5` (tracking, session 2): stale ['xelvoria', 'zorvista premium'] -> current ['daily journal subscription']
   - `@overlay/subscriptions/xelvoria`: "Subscription to Xelvoria" / "Xelvoria" / "Xelvoria subscription"
   - cards stating the current value: @overlay/subscriptions/daily-journal
24. `meme-nofiller/pl_032/update/1#5` (tracking, session 1): stale ['thyranote'] -> current ['zorvista premium']
   - `@overlay/hobbies/reading`: "- User manages and tracks reading and notes using [[tools/thyranote]]."
   - `@overlay/tools/thyranote`: "Thyranote Reading Tracker Subscription" / "Thyranote" / "Thyranote subscription"
   - cards stating the current value: @overlay/entertainment/zorvista-premium
25. `meme-nofiller/pl_049/update/2#5` (tracking, session 2): stale ['xelvoria', 'dranthazon'] -> current ['pyrethon plus']
   - `@overlay/music/guitar`: "- The user uses [[subscriptions/xelvoria]] for musician resources."
   - `@overlay/subscriptions/xelvoria`: "Xelvoria Platform Subscription" / "Xelvoria" / "Xelvoria platform"
   - cards stating the current value: @overlay/subscriptions/pyrethon-plus
26. `meme-nofiller/sw_033/update/4#1` (root, session 4): stale ['seokjin kang'] -> current ['jihoon ryu']
   - `@overlay/engineering/code-review-policy`: "- Lead approval for core/ is provided by team lead [[team/team-lead]] (Seokjin Kang)."
   - `@overlay/engineering/package-manager-synthari`: "- Team lead [[team/team-lead]] (Seokjin Kang) is guiding the team through the transition to Synthari Modules."
   - cards stating the current value: @overlay/team/team-lead-jihoon-ryu, @overlay/team/weekly-report-recipient-james-lee
27. `meme-nofiller/pl_039/update/4#1` (root, session 4): stale ['ms in cs at quessara university'] -> current ['online bootcamp (coding)']
   - `@overlay/work/bike-commute`: "The user takes their bike to work, a routine that depends on studying for an MS in CS at Quessara University and would change if their school changes." / "- Biking to work depends on the user studying for an [[education/quessara-university|MS in CS at Quessara University]]; if that changes, this commute would change too."
   - cards stating the current value: none
28. `meme-nofiller/pl_042/update/4#1` (root, session 4): stale ['pre-diabetes'] -> current ['high blood pressure']
   - `@overlay/health/diet`: "- Aligns dietary habits with managing metabolic health and blood sugar [[health/pre-diabetes]]."
   - cards stating the current value: @overlay/health/high-blood-pressure
29. `meme-nofiller/pl_011/update/4#1` (root, session 4): stale ['tendinitis'] -> current ['seasonal allergies']
   - `@overlay/user/hobbies/running-club`: "- They are mindful of pacing, recovery, and technique to stay active while managing physical health and conditions such as [[user/health/tendinitis]]."
   - cards stating the current value: @overlay/user/health/seasonal-allergies
30. `meme-nofiller/pl_041/update/2#5` (tracking, session 2): stale ['dranthis pickup', 'vorantel suv'] -> current ['xylorim scooter']
   - `@overlay/vehicles/planned-electric-car`: "- Currently drives a [[vehicles/current-vehicle]] (Dranthis Pickup)."
   - cards stating the current value: @overlay/vehicles/xylorim-scooter
31. `meme-nofiller/pl_037/update/2#5` (tracking, session 2): stale ['a daily news podcast'] -> current ['a history documentary series']
   - `@overlay/media/daily-news-podcasts`: "The user regularly listens to a daily news podcast to stay updated on current events while doing other things, preferring a mix of news for a well-rounded perspective." / "- The user's current media habit is listening to a daily news podcast (as of March 2023)."
   - cards stating the current value: @overlay/media/history-documentary-series
32. `meme-nofiller/pl_024/update/2#5` (tracking, session 2): stale ['sarah', 'jessica'] -> current ['taylor']
   - `@overlay/hobbies/video-games`: "The user plays video games as a major hobby, favoring action-adventure and RPG open-world games, and often plays together with partner Sarah." / "- Frequently plays video games together with partner [[relationships/partner-sarah|Sarah]], finding shared gaming especially enjoyable."
   - cards stating the current value: @overlay/hobbies/hiking, @overlay/relationships/partner-taylor
33. `meme-nofiller/pl_032/update/2#5` (tracking, session 2): stale ['thyranote', 'zorvista premium'] -> current ['meal kit (kelvimeal)']
   - `@overlay/entertainment/zorvista-premium`: "Zorvista Premium Streaming Subscription" / "Zorvista Premium" / "The user is subscribed to Zorvista Premium as of March 2023, appreciating its selection of television shows."
   - `@overlay/hobbies/reading`: "- User manages and tracks reading and notes using [[tools/thyranote]]."
   - `@overlay/tools/thyranote`: "Thyranote Reading Tracker Subscription" / "Thyranote" / "Thyranote subscription"
   - cards stating the current value: none
34. `meme-nofiller/pl_014/update/1#7` (tracking, session 1): stale ['daily journal subscription'] -> current ['dranthazon']
   - `@overlay/habits/journaling`: "Daily Journal Subscription and Routine"
   - cards stating the current value: @overlay/subscriptions/dranthazon
35. `meme-nofiller/pl_009/update/4#1` (root, session 4): stale ['tendinitis'] -> current ['chronic migraine']
   - `@overlay/interests/running`: "- Navigates physical activity challenges alongside tendinitis [[health/tendinitis]]."
   - cards stating the current value: @overlay/health/chronic-migraine, @overlay/health/dietary-restriction-no-alcohol, @overlay/health/exercise-routine-yoga
36. `meme-nofiller/pl_022/update/2#3` (tracking, session 2): stale ['james', 'alex'] -> current ['taylor']
   - `@overlay/hobbies/tennis`: "Tennis Hobby and Practice with Alex" / "tennis partner Alex" / "Alex tennis"
   - `@overlay/hobbies/woodworking`: "- The user's partner [[personal/partner|James]] is very supportive of their woodworking endeavors."
   - cards stating the current value: @overlay/hobbies/wine-tasting, @overlay/personal/partner-taylor
37. `meme-nofiller/pl_040/update/1#5` (tracking, session 1): stale ['zyvanta sedan'] -> current ['quorvel ev']
   - `@overlay/transport/bus-commute`: "- The user also owns and drives a Zyvanta Sedan ([[transport/vehicle]])."
   - cards stating the current value: @overlay/transport/quorvel-ev
38. `meme-nofiller/pl_048/update/1#3` (tracking, session 1): stale ['jessica'] -> current ['alex']
   - `@overlay/hobbies/woodworking`: "- Collaborates on woodworking projects with partner [[personal/partner-jessica]]." / "- Has built both decorative pieces and functional items such as shelves with Jessica."
   - cards stating the current value: @overlay/hobbies/cycling, @overlay/personal/partner-alex
39. `meme-nofiller/pl_046/update/2#5` (tracking, session 2): stale ['xelvoria'] -> current ['dranthazon']
   - `@overlay/user/hobbies/pottery`: "- The user looks for tutorials and tips across different art forms on [[user/subscriptions/xelvoria]] to inspire their art and pottery practice."
   - cards stating the current value: @overlay/user/subscriptions/dranthazon
40. `meme-nofiller/sw_009/update/4#1` (root, session 4): stale ['narvex cloud'] -> current ['orinthal serve']
   - `@overlay/team/release-schedule`: "- Production deployments are executed to Narvex Cloud ([[team/deployment]])."
   - cards stating the current value: @overlay/team/deployment-orinthal-serve
41. `meme-nofiller/pl_036/update/2#5` (tracking, session 2): stale ['james', 'jordan'] -> current ['taylor']
   - `@overlay/user/fitness/running`: "The user is a member of a running club, actively training to improve running performance and considering running with partner Jordan." / "- The user values training with a partner or buddy, specifically partner Jordan ([[user/relationships/partner-jordan]]), to enhance motivation and consistency."
   - `@overlay/user/hobbies/art`: "- The user's partner James ([[user/relationships/partner]]) is supportive of their art hobby."
   - cards stating the current value: @overlay/user/hobbies/wine-tasting, @overlay/user/relationships/partner-taylor
42. `meme-nofiller/sw_038/update/4#1` (root, session 4): stale ['synthari'] -> current ['dravex']
   - `@overlay/tooling/dev-server`: "Local Development Server: synthari launch --hmr" / "synthari launch" / "synthari launch --hmr"
   - `@overlay/tooling/package-manager-synthari`: "Team Package Manager: Synthari Modules" / "Synthari Modules" / "Synthari package manager"
   - cards stating the current value: @overlay/tooling/framework-dravex
43. `meme-nofiller/pl_032/update/4#1` (root, session 4): stale ['in a relationship'] -> current ['married']
   - `@overlay/finances/house-down-payment`: "- User is in a relationship ([[personal/relationship-status]]) and considers how being in a relationship impacts financial planning when saving for a house."
   - cards stating the current value: @overlay/personal/marital-status, @overlay/personal/partner
44. `meme-nofiller/pl_034/update/4#1` (root, session 4): stale ['seasonal allergies'] -> current ['lactose intolerance']
   - `@overlay/health/seasonal-allergies-resolved`: "Seasonal allergies treated and resolved" / "seasonal allergies resolved" / "seasonal allergies treated"
   - cards stating the current value: @overlay/dietary/lactose-intolerance
45. `meme-nofiller/pl_028/update/1#5` (tracking, session 1): stale ['zorvista premium'] -> current ['dranthazon']
   - `@overlay/subscriptions/zorvista-premium`: "User Subscription: Zorvista Premium" / "Zorvista Premium" / "The user subscribes to Zorvista Premium, enjoying its features and catalog of shows and content."
   - cards stating the current value: @overlay/hobbies/basketball, @overlay/subscriptions/dranthazon
46. `meme-nofiller/pl_019/update/4#1` (root, session 4): stale ['single'] -> current ['in a relationship']
   - `@overlay/personal/living-situation`: "- Maintains a household with family alongside an independent, single lifestyle ([[personal/relationship-status]])."
   - cards stating the current value: @overlay/personal/in-a-relationship
47. `meme-nofiller/sw_019/update/4#1` (root, session 4): stale ['narvex cloud'] -> current ['zephyra platform']
   - `@overlay/team/release-schedule`: "- Releases are deployed to Narvex Cloud (see [[tech-stack/narvex-cloud]])."
   - cards stating the current value: @overlay/tech-stack/deploy-command-zephyra, @overlay/tech-stack/log-drain-korinth, @overlay/tech-stack/zephyra-platform
48. `meme-nofiller/pl_022/update/4#1` (root, session 4): stale ['quivira springs community college'] -> current ['online bootcamp (coding)']
   - `@overlay/hobbies/wine-tasting`: "- The user balances attending wine tasting club activities with studying at [[personal/education|Quivira Springs Community College]]."
   - `@overlay/personal/education`: "Studies at Quivira Springs Community College" / "Quivira Springs Community College" / "The user is studying at Quivira Springs Community College as of March 2023, finding it challenging to balance school with hobbies and social activities."
   - `@overlay/personal/financial-goal`: "The user's financial goal is saving for their kids' education fund, determined by studying at Quivira Springs Community College; priorities shift if that changes." / "- This financial goal is determined by the fact that the user is studying at [[personal/education|Quivira Springs Community College]]." / "- If the user's educational situation at Quivira Springs Community College changes, their financial priorities would shift."
   - `@overlay/personal/financial-goal-wedding`: "- The wedding savings goal depends on the user's schooling status at [[personal/education|Quivira Springs Community College]]." / "- If the user transfers or departs from Quivira Springs Community College, their financial priority shifts immediately to wedding savings." / "- While the user remains enrolled at Quivira Springs Community College, the active financial priority remains the kids' education fund."
   - `@overlay/personal/potluck-group`: "- Attending the potluck dinner group is a way for the user to unwind after a busy week of school at [[personal/education|Quivira Springs Community College]]."
   - cards stating the current value: none
49. `meme-nofiller/pl_036/update/4#1` (root, session 4): stale ['thornvale crossing'] -> current ['orinthal park']
   - `@overlay/user/hobbies/wine-tasting`: "- The user is interested in discovering places that offer wine tasting near their home in Thornvale Crossing ([[user/location/residence]])."
   - cards stating the current value: @overlay/user/location/residence-orinthal-park, @overlay/user/social/game-night
50. `meme-nofiller/sw_042/update/4#1` (root, session 4): stale ['seokjin kang'] -> current ['yuna park']
   - `@overlay/team/escalations`: "- Works alongside team lead [[team/lead]] Seokjin Kang on team coordination and resolution."
   - `@overlay/team/meetings`: "- Team lead [[team/lead]] Seokjin Kang facilitates team alignment during these weekly sessions."
   - `@overlay/team/release-strategy`: "- Team processes and schedules align with [[team/lead]] Seokjin Kang and sprint targets like [[project/sprint-deadline]]."
   - `@overlay/team/weekly-report`: "- Weekly reporting aligns with team leadership under [[team/lead]] Seokjin Kang."
   - cards stating the current value: @overlay/team/lead-yuna-park

## lost

1. `meme-nofiller/sw_033/3#5` (point 3, plain, error_log): value "connectionrefusederror: [errno 111] connection refused. service crysthene-db-primary on port 5432 is not accepting connections. last successful heartbeat was at 2024-03-15t08:23:41z. check firewall rules and verify that max_connections has not been exceeded"
   - `@overlay/engineering/crysthene-db-error`: "Error Log: crysthene-db-primary Connection Refused" / "crysthene-db-primary error"
   - `@overlay/engineering/package-manager (inactive)`: "- The user noted Karnex Pack has been efficient for managing dependencies."
   - `@overlay/engineering/default-branch`: "- The trunk branch is used as the primary base branch for development, extending the branching strategy described in [[engineering/branching-strategy]]."
   - `@overlay/engineering/production-logs`: "production log drain" / "velturis log stream"
   - `@overlay/team/oncall-rotation`: "primary secondary oncall" / "The team uses a paired on-call rotation with a primary and a secondary person on duty."
   - `@overlay/team/team-lead`: "- Recommended communication practices with Seokjin Kang include regular check-ins, open feedback channels, and addressing transition challenges directly."
2. `meme-nofiller/pl_017/3#3` (point 3, dependent, regular_appointment): value "physical therapy (2x/week)"
   - `@overlay/user/health/physical-therapy`: "Regular Appointment: Physical Therapy" / "physical therapy"
   - `@overlay/user/health/chiropractor`: "Contingency Appointment: Chiropractor" / "chiropractor appointment"
   - `@overlay/user/fitness/thandrel-ymca`: "- Regular gym and workout venue is Thandrel YMCA while living at Belvona Harbor."
3. `meme-nofiller/pl_022/3#3` (point 3, dependent, work_schedule): value "9-to-5 fixed"
   - `@overlay/personal/work-hours`: "Work Hours: Fixed 9-to-5 Schedule" / "work hours"
   - `@overlay/personal/commute`: "Commuting to Work by Car" / "work commute"
   - `@overlay/personal/education`: "- The user has a busy academic schedule at Quivira Springs Community College and uses social meetups to unwind."
   - `@overlay/plans/laptop-purchase`: "The user is planning to purchase a new laptop, evaluating specifications needed to support their woodworking design work and Japanese language learning."
4. `meme-nofiller/pl_027/3#1` (point 3, dependent, commute_duration): value "10 min"
   - `@overlay/user/commute/work-commute`: "Work Commute by Subway and Bus" / "work commute"
5. `meme-nofiller/pl_040/0#11` (point end, plain, media_consumption): value "whispers of zarinthea (tv)"
   - `@overlay/media/whispers-of-zarinthea`: "Whispers of Zarinthea TV show" / "Whispers of Zarinthea"
6. `meme-nofiller/pl_008/2#9` (point 3, plain, work_schedule): value "shift work (night)"
   - `@overlay/career/work-schedule`: "Night Shift Work Schedule" / "night shift"
   - `@overlay/relationships/partner`: "The user's partner is named James, providing mutual support while navigating the user's night shift schedule." / "- The user values having James to share life with, noting it makes a big difference especially when dealing with a night shift schedule [[career/work-schedule]]."
   - `@overlay/career/occupation`: "- Their work keeps them actively engaged with various technical challenges and projects."
   - `@overlay/career/office-location`: "work location"
   - `@overlay/career/work-project`: "Current Work Project: Backend Migration" / "work project"
   - `@overlay/transportation/commute (inactive)`: "commute to work"
   - `@overlay/transportation/work-commute`: "Walking Commute to Work" / "walking to work"
7. `meme-nofiller/sw_030/3#7` (point end, plain, error_log): value "panicexception: thread 'tokio-runtime-worker' panicked at 'index out of bounds: the len is 0 but the index is 5', src/handlers/auth.rs:142:23. stack trace shows recursive call in middleware_chain to request_validator to token_parser. restart triggered automatic failover at 2024-04-02t14:18:33z"
   - `@overlay/devops/auth-panic-error`: "Error Log: Auth Handler Panic and Failover Incident" / "auth panic error log"
   - `@overlay/tech-stack/database-connection`: "- The connection string depends directly on [[tech-stack/database]] (Crysthene DB); if the database changes, this connection string will change." / "- Necessary application configuration changes must be mapped out prior to updating the database connection string."
   - `@overlay/tech-stack/database-thalnex`: "- The user asked for tips and things to watch out for during the transition to Thalnex Store." / "- Supersedes [[tech-stack/database]] in the core application stack alongside [[tech-stack/design-system]] and [[tech-stack/package-manager-veltrion]]."
   - `@overlay/devops/database-backups`: "- Backups protect data integrity and ensure high availability for [[tech-stack/database]] (Crysthene DB)."
   - `@overlay/devops/on-call-rotation`: "On-Call Rotation: Weekly Mon-Sun Rotation" / "on-call rotation"
   - `@overlay/devops/release-schedule`: "- Aligns with deployment workflows referencing [[git/default-branch]], database migrations in [[tech-stack/migrations]], and [[devops/runbooks]]."
   - `@overlay/devops/runbooks`: "- Supports operational response across project systems such as [[tech-stack/database]] and development workflow [[git/default-branch]]."
   - `@overlay/devops/secret-manager`: "- The user inquired about tips and things to watch out for when using Cryptara Vault." / "- Planning and executing proper application integration is key when rolling out Cryptara Vault across services."
   - `@overlay/git/code-review-policy`: "Code Review Policy: 2 Approvals and Security Review for auth/" / "auth review policy"
   - `@overlay/tech-stack/database (inactive)`: "- Part of the core application stack alongside [[tech-stack/design-system]] and [[tech-stack/package-manager]]."
8. `meme-nofiller/sw_006/2#1` (point 3, plain, standup_format): value "async written updates in slack"
   - `@overlay/team/standup`: "Team Standup Format - Async Slack Updates" / "standup format"
   - `@overlay/team/approval-authority`: "- Regular check-ins and updates with Soyeon Park help ensure alignment and clear expectations."
   - `@overlay/team/weekly-reports`: "- Keep updates concise and focus on key takeaways for reporting."
   - `@overlay/tech/design-system`: "- Best practices include ensuring team familiarity through regular training and documentation updates." / "- A version control process for design system updates helps manage component changes without disruption."
9. `meme-nofiller/sw_012/0#9` (point 3, plain, standup_format): value "async written updates in slack"
   - `@overlay/process/standup`: "Slack Asynchronous Written Standup Format" / "standup format"
   - `@overlay/auth/token-format`: "auth token format" / "The team uses the Cerberix-SAML-assertion token format for authentication and managing user sessions and access."
   - `@overlay/database/migrations`: "- Schema changes and database structure updates are applied using Zyndra Alter."
   - `@overlay/project/changelog`: "The project changelog is hosted on the GitHub Releases page for tracking updates and release changes." / "- Used for tracking updates, version changes, and release history across the project."
10. `meme-nofiller/sw_002/3#11` (point 3, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/aurora/error-log-vorathis`: "Aurora Error Log - SegmentationFault in vorathis_query_planner.so" / "vorathis_query_planner.so crash"
   - `@overlay/aurora/ci-config`: "Aurora CI Config - orinthal-build.yml" / "Aurora CI config"
   - `@overlay/aurora/code-review-policy`: "Aurora Code Review Policy - Lead Approval for Core" / "core directory reviews"
   - `@overlay/aurora/deploy-command`: "Aurora Deploy Command - orinthal publish --tier production" / "Aurora deploy command"
   - `@overlay/aurora/design-system`: "Aurora Design System - Synthari Elements v1.2" / "Aurora design system"
   - `@overlay/aurora/dockerfile`: "Aurora Dockerfile - deploy/Dockerfile.korinth" / "Aurora Dockerfile"
   - `@overlay/aurora/log-drain`: "Aurora Log Drain - stream.velturis.io/aurora" / "Aurora log drain"
   - `@overlay/aurora/test-coverage`: "Aurora Test Coverage Target - 90% Core Modules" / "core modules coverage"
   - `@overlay/aurora/cloud-deployment`: "Aurora Cloud Deployment - Narvex Cloud" / "Aurora cloud deployment"
   - `@overlay/aurora/default-branch`: "Aurora Default Branch - develop" / "Aurora default branch"
11. `meme-nofiller/sw_034/2#5` (point 3, plain, project_structure): value "workspace with /services and /common"
   - `@overlay/dev/workspace-structure`: "Project Workspace Structure (/services and /common)" / "workspace structure"
   - `@overlay/dev/build-command`: "project build command" / "- The project build command is `pyronis pack --quick` as of March 2023."
   - `@overlay/dev/build-tool`: "project build tool" / "- The team uses Pyronis Build as their project build tool as of March 2023."
   - `@overlay/dev/test-command`: "project test command" / "- The project test command is `tarvex verify --all` as of March 2023."
   - `@overlay/dev/test-tool`: "- Tarvex Verify is responsible for running test suites and verification across the project."
   - `@overlay/docs/onboarding-guide`: "- Dedicated to helping new team members get integrated smoothly into the project, complementing [[docs/project-docs|general project documentation]]."
   - `@overlay/docs/project-docs`: "Aurora Team Project Documentation Repository" / "project docs"
   - `@overlay/tech-stack/design-system`: "- Used for creating consistent UI components across the project."
   - `@overlay/tech-stack/framework`: "project framework" / "The team uses Veltrion as their project framework alongside the Veltrion UI Kit v2."
12. `meme-nofiller/pl_008/2#9` (point end, plain, work_schedule): value "shift work (night)"
   - `@overlay/career/work-schedule`: "Night Shift Work Schedule" / "night shift"
   - `@overlay/relationships/partner`: "The user's partner is named James, providing mutual support while navigating the user's night shift schedule." / "- The user values having James to share life with, noting it makes a big difference especially when dealing with a night shift schedule [[career/work-schedule]]."
   - `@overlay/career/occupation`: "- Their work keeps them actively engaged with various technical challenges and projects."
   - `@overlay/career/office-location`: "work location"
   - `@overlay/career/work-project`: "Current Work Project: Backend Migration" / "work project"
   - `@overlay/transportation/work-commute`: "Walking Commute to Work" / "walking to work"
13. `meme-nofiller/sw_050/2#7` (point end, plain, test_coverage_target): value "70% overall, 95% for auth"
   - `@overlay/aurora/test-coverage-targets`: "Aurora Test Coverage Targets" / "test coverage targets"
   - `@overlay/aurora/infrastructure (inactive)`: "aurora deployment target"
   - `@overlay/aurora/infrastructure-zephyra`: "aurora deployment target"
   - `@overlay/aurora/sprint-deadline`: "sprint target date"
   - `@overlay/aurora/staging-environment`: "- Staging is used to verify and test releases prior to production deployments."
14. `meme-nofiller/pl_010/3#7` (point end, rule, travel_plan): value "zynthera bay beach trip (1 week)"
   - `@overlay/travel/zynthera-bay-trip`: "Zynthera Bay Beach Trip Contingency Plan" / "Zynthera Bay"
   - `@overlay/travel/mountain-ski-trip`: "Mountain Ski Trip Plan" / "ski trip"
   - `@overlay/finances/engagement-ring-purchase`: "- This purchase plan connects to being engaged [[lifestyle/engaged-relationship-status]]."
15. `meme-nofiller/pl_025/2#11` (point end, plain, media_consumption): value "the veldrakon spiral (tv)"
   - `@overlay/media/the-veldrakon-spiral`: "Current Media: The Veldrakon Spiral (TV Series)" / "The Veldrakon Spiral"
16. `meme-nofiller/pl_038/3#3` (point 3, dependent, travel_plan): value "cross-country road trip (2 weeks)"
   - `@overlay/plans/cross-country-road-trip`: "Travel Plans: Cross-Country Road Trip" / "cross-country road trip"
   - `@overlay/plans/island-getaway`: "Travel Plans: Island Getaway Contingency" / "relationship status change trip"
   - `@overlay/transportation/planned-electric-car (inactive)`: "EV purchase plan"
17. `meme-nofiller/sw_001/3#11` (point 3, plain, error_log): value "outofmemoryerror: java heap space. gc overhead limit exceeded after 8 consecutive failed collections in pool 'ps old gen'. heap dump written to /var/log/aurora/heap-2024-05-08.hprof at 18:42:11z. recommend increasing -xmx beyond 4g or investigating memory leak in orderprocessor"
   - `@overlay/development/order-processor-oom-error`: "OrderProcessor OutOfMemoryError Log" / "OutOfMemoryError"
   - `@overlay/meetings/standup`: "Async Written Standup Format in Slack" / "written updates"
   - `@overlay/project/docs`: "aurora docs" / "Project documentation is maintained at github.com/aurora-team/docs for onboarding and team reference."
   - `@overlay/project/incident-runbook`: "docs.aurora.internal/runbooks" / "The incident runbook for handling incidents is located at docs.aurora.internal/runbooks."
   - `@overlay/project/team-channel`: "Aurora Team Channel #aurora-dev" / "#aurora-dev"
18. `meme-nofiller/pl_027/3#3` (point 3, dependent, regular_appointment): value "physical therapy (2x/week)"
   - `@overlay/user/health/physical-therapy`: "Physical Therapy Appointments" / "physical therapy"
19. `meme-nofiller/pl_030/3#1` (point 3, dependent, insurance): value "employer + supplemental"
   - `@overlay/work/insurance`: "Work Benefits: Health Insurance" / "health insurance"
   - `@overlay/work/employer-elyndra-health`: "employer"
   - `@overlay/work/office-location`: "- This remote office location is through the user's employer, Elyndra Health [[work/employer-elyndra-health]]." / "- If the user's employer changes, the office location would change."
   - `@overlay/work/role-data-scientist`: "- The user works as a data scientist at Elyndra Health [[work/employer-elyndra-health]]."
   - `@overlay/work/schedule`: "- The user's day shift work schedule is through their employer, Elyndra Health [[work/employer-elyndra-health]]." / "- If the user's employer changes, their work hours would change."
20. `meme-nofiller/sw_005/0#9` (point 3, plain, standup_format): value "15-min daily video call"
   - `@overlay/aurora/standup`: "Aurora Team Daily Standup Format" / "team standup"
   - `@overlay/aurora/team-meeting`: "- Format: Team discussion / sync" / "- Related standup schedule: [[aurora/standup]]"
   - `@overlay/aurora/sprint-deadline (inactive)`: "- Related team syncs: [[aurora/team-meeting]] and [[aurora/standup]]"
   - `@overlay/aurora/sprint-deadline-2025-05-23 (inactive)`: "- Related team syncs: [[aurora/team-meeting]] and [[aurora/standup]]"
   - `@overlay/aurora/sprint-deadline-2025-06-06`: "- Related team syncs: [[aurora/team-meeting]] and [[aurora/standup]]"
21. `meme-nofiller/sw_026/3#11` (point 3, plain, error_log): value "outofmemoryerror: java heap space. gc overhead limit exceeded after 8 consecutive failed collections in pool 'ps old gen'. heap dump written to /var/log/aurora/heap-2024-05-08.hprof at 18:42:11z. recommend increasing -xmx beyond 4g or investigating memory leak in orderprocessor"
   - `@overlay/ops/oom-error`: "Error Log: OrderProcessor OutOfMemoryError Java Heap Space" / "OutOfMemoryError"
   - `@overlay/ops/runbook`: "Incident Runbook: notion.so/aurora-team/incidents" / "notion.so/aurora-team/incidents"
   - `@overlay/project/documentation`: "Project Documentation Site: docs.aurora.internal/wiki" / "docs.aurora.internal/wiki"
22. `meme-nofiller/sw_049/3#7` (point 3, plain, error_log): value "certificateverificationerror: certificate chain validation failed for crysthene-db-primary.internal. subject cn does not match expected hostname; chain depth 2 unverified. observed at 2024-07-22t11:09:47z by tls_handshake_listener. rotate the cert via cryptara vault and restart the connection pool to recover"
   - `@overlay/ops/crysthene-db-cert-error`: "Certificate Verification Error: crysthene-db-primary.internal" / "CertificateVerificationError"
   - `@overlay/ops/incident-runbook`: "internal runbooks" / "The team's incident runbook is hosted at docs.aurora.internal/runbooks for incident handling."
   - `@overlay/project/onboarding-guide`: "internal onboarding" / "docs.aurora.internal/onboarding"
23. `meme-nofiller/sw_006/3#5` (point end, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/tech/vorathis-query-planner-error`: "Error Log - vorathis_query_planner.so SegmentationFault" / "vorathis error log"
   - `@overlay/team/channel`: "Team Communication Channel - #aurora-dev" / "#aurora-dev"
   - `@overlay/team/incident-runbook`: "Incident Runbook - wiki.aurora.dev/incident-response" / "wiki.aurora.dev/incident-response"
   - `@overlay/team/onboarding`: "Onboarding Guide - notion.so/aurora-team/new-hire" / "notion.so/aurora-team/new-hire"
   - `@overlay/team/standup`: "- Standup updates are structured around three main points: accomplishments since last update, next tasks, and any blockers."
24. `meme-nofiller/sw_034/3#9` (point end, plain, error_log): value "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status = 'shipped' where region = 'us-east'. query 2 was delete from orders where created_at < now() - interval '30 days'. first seen at 2024-08-04t22:33:18z; recommend serializable isolation review"
   - `@overlay/ops/aurora-orders-deadlock`: "Aurora Orders Table Deadlock Error Log" / "DeadlockDetected error log"
   - `@overlay/dev/build-tool`: "- Build tool operations and packaging are managed through Pyronis Build."
   - `@overlay/dev/code-review`: "Code Review Policy for auth/ Directory" / "code review policy"
   - `@overlay/ops/on-call-rotation`: "- Handoffs and clear communication plans ensure both members are aligned on responsibilities."
   - `@overlay/ops/production-alerts`: "Production alerts are sent to the #zenith-incidents channel for monitoring and incident tracking." / "- Production alerts are routed to the `#zenith-incidents` channel as of March 2023."
   - `@overlay/tech-stack/synthari-framework`: "- Core development and project features are built using the Synthari framework."
25. `meme-nofiller/pl_007/3#1` (point 3, dependent, regular_appointment): value "dermatologist (monthly)"
   - `@overlay/health/regular-appointment-dermatologist`: "Regular Dermatologist Appointment" / "dermatologist appointment"
   - `@overlay/entertainment/book-xelvari-dawn`: "- Reading Xelvari Dawn is part of the user's monthly reading for their [[social/monthly-book-club]]."
   - `@overlay/health/contingent-therapy-appointment`: "Contingent Weekly Therapy Appointment Upon Relocation" / "therapy appointment"
   - `@overlay/social/monthly-book-club`: "Monthly Book Club" / "monthly book club"
   - `@overlay/social/wednesday-trivia-night`: "The user's regular social meetup is trivia night on Wednesdays, which they enjoy for unwinding and testing knowledge as of March 2023." / "- On 2023-03-01, the user shared that their regular social meetup is trivia night on Wednesdays."
26. `meme-nofiller/pl_041/4#3` (point end, plain, media_consumption): value "thyrelion (anime)"
   - `@overlay/media/current-media`: "Current Media: Thyrelion" / "Thyrelion"
27. `meme-nofiller/sw_036/3#11` (point end, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/team/query-planner-segfault`: "Segmentation fault error log in vorathis_query_planner.so" / "vorathis_query_planner.so crash"
   - `@overlay/team/logging-drain`: "Team log drain destination stream.velturis.io/aurora" / "log drain"
   - `@overlay/team/changelog`: "Team changelog notion.so/aurora-team/releases" / "notion.so/aurora-team/releases"
   - `@overlay/team/ci-config`: "orinthal-build.yml" / "The CI config is thandrel-flow.toml, determined by deploying on Narvex Cloud; if deploy targets change, it will be orinthal-build.yml."
   - `@overlay/team/docker-image`: "Team Docker image narvex-registry/aurora:latest" / "narvex-registry/aurora:latest"
   - `@overlay/team/dockerfile-path`: "aurora Dockerfile" / "The Dockerfile is at infra/narvex/Dockerfile, determined by the Docker image narvex-registry/aurora:latest; if the image changes, this would change."
   - `@overlay/team/incident-runbook`: "Team incident runbook github.com/aurora-team/runbooks" / "github.com/aurora-team/runbooks"
   - `@overlay/team/monitoring-dashboard`: "Team monitoring dashboard metrics.thandrel.io/aurora-prod" / "metrics.thandrel.io/aurora-prod"
   - `@overlay/team/onboarding-guide`: "Team onboarding guide docs.aurora.internal/onboarding" / "docs.aurora.internal/onboarding"
   - `@overlay/team/sprint-deadline`: "aurora sprint deadline"
28. `meme-nofiller/sw_035/2#7` (point end, plain, standup_format): value "monday/thursday sync, async rest"
   - `@overlay/project/standup-format`: "Team Standup Format" / "standup format"
   - `@overlay/project/team-meeting`: "Monday 11am meeting" / "team sync"
29. `meme-nofiller/sw_019/3#15` (point end, rule, ci_config): value "deleted"
   - `@overlay/tech-stack/deploy-command (inactive)`: "The deploy command is korinth release --prod; if CI config changes, the deploy command will be zephyra push --target prod." / "- Determined by the CI configuration being orinthal-build.yml (see [[tech-stack/ci-config]])."
   - `@overlay/tech-stack/deploy-command-zephyra`: "The deploy command is zephyra push --target prod following the CI config change." / "- Triggered by CI config change and removal (supersedes [[tech-stack/deploy-command]])."
30. `meme-nofiller/sw_047/4#3` (point end, plain, onboarding_guide): value "onboarding.md in repo root"
   - `@overlay/workflow/onboarding-guide`: "Onboarding Guide Location: ONBOARDING.md" / "ONBOARDING.md"
31. `meme-nofiller/pl_020/3#1` (point 3, dependent, regular_appointment): value "dentist (every 6 months)"
   - `@overlay/health/dentist-appointments`: "Regular Dental Appointments" / "dentist appointments"
32. `meme-nofiller/sw_025/3#5` (point 3, plain, error_log): value "certificateverificationerror: certificate chain validation failed for crysthene-db-primary.internal. subject cn does not match expected hostname; chain depth 2 unverified. observed at 2024-07-22t11:09:47z by tls_handshake_listener. rotate the cert via cryptara vault and restart the connection pool to recover"
   - `@overlay/security/crysthene-db-cert-error`: "Error Log: CertificateVerificationError for crysthene-db-primary.internal" / "CertificateVerificationError"
   - `@overlay/development/default-branch`: "primary branch"
33. `meme-nofiller/sw_019/3#13` (point end, plain, error_log): value "panicexception: thread 'tokio-runtime-worker' panicked at 'index out of bounds: the len is 0 but the index is 5', src/handlers/auth.rs:142:23. stack trace shows recursive call in middleware_chain to request_validator to token_parser. restart triggered automatic failover at 2024-04-02t14:18:33z"
   - `@overlay/incidents/auth-panic-error`: "Error Log: PanicException in src/handlers/auth.rs" / "PanicException auth.rs"
   - `@overlay/tech-stack/deploy-command-zephyra`: "- Triggered by CI config change and removal (supersedes [[tech-stack/deploy-command]])." / "- Associated with deployment on Zephyra Platform (see [[tech-stack/zephyra-platform]])."
   - `@overlay/tech-stack/log-drain (inactive)`: "[INACTIVE] Log Drain: drain.zephyra.io/proj-42" / "log drain"
   - `@overlay/tech-stack/log-drain-korinth`: "Log Drain: logs.korinth.dev/aurora" / "log drain"
   - `@overlay/team/incident-runbook`: "- Used in incident response alongside the alerts channel (see [[team/production-alerts]]) and on-call rotation (see [[team/on-call-rotation]])."
   - `@overlay/team/on-call-rotation`: "Team On-Call Rotation and Weekly Signup" / "on-call rotation"
   - `@overlay/team/production-alerts`: "- Ties into team incident response and on-call monitoring (see [[team/on-call-rotation]])."
   - `@overlay/team/release-schedule`: "- Releases are deployed to Narvex Cloud (see [[tech-stack/narvex-cloud]])."
   - `@overlay/tech-stack/deploy-command (inactive)`: "- Determined by the CI configuration being orinthal-build.yml (see [[tech-stack/ci-config]])."
   - `@overlay/tech-stack/docker-image`: "- Deployed to Narvex Cloud infrastructure (see [[tech-stack/narvex-cloud]])." / "- Determines the Dockerfile location (see [[tech-stack/dockerfile]])."
34. `meme-nofiller/sw_038/2#7` (point end, plain, standup_format): value "async written updates in slack"
   - `@overlay/operations/standup-format`: "Team Standup Format: Async Slack Updates" / "standup format"
   - `@overlay/project/changelog`: "The project changelog is hosted at docs.aurora.internal/changelog to keep track of updates and changes." / "- The changelog serves as a handy location to track all updates, modifications, and changes made to the project."
35. `meme-nofiller/sw_018/3#9` (point 3, plain, error_log): value "outofmemoryerror: java heap space. gc overhead limit exceeded after 8 consecutive failed collections in pool 'ps old gen'. heap dump written to /var/log/aurora/heap-2024-05-08.hprof at 18:42:11z. recommend increasing -xmx beyond 4g or investigating memory leak in orderprocessor"
   - `@overlay/incidents/order-processor-oom-error`: "Error Log: OutOfMemoryError in OrderProcessor" / "OutOfMemoryError"
   - `@overlay/process/changelog`: "Aurora Team Release Changelog" / "notion.so/aurora-team/releases"
   - `@overlay/process/incident-runbook`: "Incident Runbook: wiki.aurora.dev/incident-response" / "wiki.aurora.dev/incident-response"
   - `@overlay/process/production-alerts`: "Production Alerts Channel: #aurora-pager" / "#aurora-pager"
   - `@overlay/process/standup`: "- The asynchronous text format was adopted to keep the team updated without the pressure or scheduling overhead of a live meeting."
   - `@overlay/tooling/database-connection-string`: "crysthene://replica-db:5432/aurora-ro" / "vorathis://cluster-main:27017/aurora"
36. `meme-nofiller/sw_020/3#11` (point end, plain, error_log): value "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status = 'shipped' where region = 'us-east'. query 2 was delete from orders where created_at < now() - interval '30 days'. first seen at 2024-08-04t22:33:18z; recommend serializable isolation review"
   - `@overlay/aurora/deadlock-error-log`: "Aurora Orders Table Deadlock Error Log" / "DeadlockDetected"
   - `@overlay/aurora/deployment`: "- Project docs are located at [[aurora/docs]]."
   - `@overlay/aurora/logging`: "Aurora Centralized Logging and Log Drain" / "log drain"
   - `@overlay/aurora/standup`: "- Standup updates are structured as text posts to ensure accountability and smooth communication."
   - `@overlay/aurora/test-coverage`: "- Testing standards and coverage adequacy are evaluated during pull request reviews."
37. `meme-nofiller/pl_040/0#11` (point 3, plain, media_consumption): value "whispers of zarinthea (tv)"
   - `@overlay/media/whispers-of-zarinthea`: "Whispers of Zarinthea TV show" / "Whispers of Zarinthea"
38. `meme-nofiller/sw_039/3#13` (point end, plain, error_log): value "panicexception: thread 'tokio-runtime-worker' panicked at 'index out of bounds: the len is 0 but the index is 5', src/handlers/auth.rs:142:23. stack trace shows recursive call in middleware_chain to request_validator to token_parser. restart triggered automatic failover at 2024-04-02t14:18:33z"
   - `@overlay/tech-stack/auth-panic-error`: "Error Log: Tokio Worker PanicException in auth.rs" / "PanicException"
   - `@overlay/tech-stack/log-drain`: "Log Drain Destination: logs.korinth.dev/aurora" / "log drain"
   - `@overlay/project/code-review`: "- Complements testing and quality standards tracked in [[tech-stack/test-coverage]]."
   - `@overlay/project/documentation`: "- Can be used to house runbooks and incident response procedures alongside [[project/on-call-rotation]] and [[project/communication-channel]]."
   - `@overlay/project/on-call-rotation`: "On-Call Rotation: Volunteer-Based Weekly Signup" / "on-call rotation"
   - `@overlay/project/production-alerts`: "on-call alerts" / "- Works in conjunction with the team's on-call rotation ([[project/on-call-rotation]]) to ensure on-call members are alerted to issues."
   - `@overlay/tech-stack/ci-config`: "- The CI configuration is determined by the infrastructure (deployed on [[tech-stack/cloud-infrastructure]]); if that changes, this would change."
   - `@overlay/tech-stack/cloud-infrastructure-korinth-hosting`: "- Supersedes earlier deployment infrastructure on Thandrel Infra ([[tech-stack/cloud-infrastructure]])."
   - `@overlay/tech-stack/deploy-command`: "- The deploy command is determined by the CI configuration being [[tech-stack/ci-config]] (orinthal-build.yml); if CI changes, this would change."
   - `@overlay/tech-stack/design-system`: "- Mentioned on 2023-03-01 during project tech stack discussion."
39. `meme-nofiller/pl_036/3#7` (point end, rule, commute_duration): value "10 min"
   - `@overlay/user/transportation/commute-duration`: "Commute Duration from Thornvale Crossing" / "commute duration"
   - `@overlay/user/fitness/running`: "- Running forms a core part of the user's active lifestyle alongside cycling ([[user/transportation/commute]])."
   - `@overlay/user/food/meal-kit`: "- The meal kit service helps the user navigate a busy schedule and balance work with hobbies like biking ([[user/transportation/commute]]) and art ([[user/hobbies/art]])."
   - `@overlay/user/hobbies/art`: "- The user balances work and hobbies like art and biking ([[user/transportation/commute]])."
   - `@overlay/user/transportation/commute`: "Work Commute by Bike" / "bike commute"
40. `meme-nofiller/pl_019/2#5` (point end, plain, media_consumption): value "thyrelion (anime)"
   - `@overlay/media/anime/thyrelion`: "Current Media: Thyrelion Anime" / "Thyrelion"
   - `@overlay/media/video-games`: "- Reflects user's interest in interactive entertainment alongside [[media/anime/thyrelion]] and [[media/podcasts/daily-news]]."
   - `@overlay/media/books/quorath-codex (inactive)`: "User's current reading media as of March 2023 is "The Quorath Codex"." / "- Current media is the book titled "The Quorath Codex" as of 2023-03-01."
41. `meme-nofiller/sw_007/4#7` (point end, plain, changelog_location): value "changelog.md in repo root"
   - `@overlay/ops/changelog`: "Project Changelog Location" / "changelog"
   - `@overlay/ops/incident-runbook`: "Incident Runbook Location"
42. `meme-nofiller/sw_012/3#7` (point end, plain, error_log): value "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status = 'shipped' where region = 'us-east'. query 2 was delete from orders where created_at < now() - interval '30 days'. first seen at 2024-08-04t22:33:18z; recommend serializable isolation review"
   - `@overlay/database/deadlock-error`: "Aurora Orders Table Deadlock Error Log" / "aurora_orders deadlock"
   - `@overlay/process/standup`: "- Standup updates are conducted asynchronously to keep everyone in the loop without needing to coordinate meeting schedules." / "- Team members post their daily status and progress updates directly in Slack."
   - `@overlay/project/changelog`: "- Team members and users refer to the GitHub Releases page to review release notes and changes." / "- Release updates and new features are documented on GitHub Releases."
   - `@overlay/database/backup-schedule`: "- Backups are performed on the schedule of 2:00 UTC and 14:00 UTC every day."
   - `@overlay/database/keldaris (inactive)`: "- Database migration tools and practices are managed to support schema evolutions in Keldaris DB."
   - `@overlay/database/migrations`: "- Schema changes and database structure updates are applied using Zyndra Alter."
   - `@overlay/database/model-syntax`: "Models are defined with Pyravar.entity('Model', attrs), determined by the use of Pyravar Mapper." / "- Database models are defined with Pyravar.entity('Model', attrs) (reported March 2023)."
   - `@overlay/database/orm`: "- Model definitions and database queries in the application are built around Pyravar Mapper."
   - `@overlay/database/thalnex-store`: "- Data migration and performance tuning are critical considerations following the switch to Thalnex Store."
   - `@overlay/process/code-review`: "Team Code Review Approval Policy" / "code review policy"
43. `meme-nofiller/sw_023/0#1` (point end, plain, oncall_rotation): value "paired oncall (primary + secondary)"
   - `@overlay/team/on-call-rotation`: "Team On-Call Rotation Setup" / "paired oncall"
   - `@overlay/team/escalation-contact`: "- Kevin Park is the primary contact person for escalations." / "- Escalations interface with incident response alongside [[ops/incident-runbook]], [[ops/production-alerts]], and [[team/on-call-rotation]]."
   - `@overlay/ops/certificate-verification-error`: "Error Log: CertificateVerificationError on crysthene-db-primary.internal" / "crysthene-db-primary.internal"
   - `@overlay/ops/incident-runbook`: "- Incident runbooks coordinate with alerts received in [[ops/production-alerts]] and the team's [[team/on-call-rotation]]."
   - `@overlay/ops/production-alerts`: "- Critical issues caught in #aurora-alerts connect with the team's incident handling and [[team/on-call-rotation]]."
   - `@overlay/team/approval-authority-contingency (inactive)`: "- This rule serves as an if-then contingency policy extending the primary approval authority assignment [[team/approval-authority]]."
44. `meme-nofiller/sw_015/3#13` (point 3, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/tech/error-log-vorathis-query-planner`: "Segmentation fault in vorathis_query_planner.so error log" / "vorathis_query_planner.so error"
   - `@overlay/tech/dockerfile`: "aurora Dockerfile" / "The Dockerfile is at deploy/Dockerfile.orinthal, determined by the Docker image orinthal-registry/aurora:deploy; if the image changes, this would change."
   - `@overlay/tech/log-drain`: "Log drain endpoint stream.velturis.io/aurora" / "stream.velturis.io/aurora"
   - `@overlay/tech/build-tool`: "Team build tool Pyronis Build" / "Pyronis Build"
   - `@overlay/tech/docker-image`: "Team Docker image orinthal-registry/aurora:deploy" / "orinthal-registry/aurora:deploy"
   - `@overlay/tech/incident-runbook`: "Incident runbook wiki.aurora.dev/incident-response" / "wiki.aurora.dev/incident-response"
   - `@overlay/tech/monitoring-dashboard`: "Monitoring dashboard status.orinthal.dev/aurora" / "status.orinthal.dev/aurora"
   - `@overlay/tech/package-manager-dranith-stack`: "- Core purpose: dependency management and package configuration across the project."
   - `@overlay/tech/production-alerts`: "Production alerts channel #aurora-pager" / "#aurora-pager"
   - `@overlay/tech/staging-environment`: "Staging environment preview.zephyra.io/aurora" / "preview.zephyra.io/aurora"
45. `meme-nofiller/sw_039/2#9` (point 3, plain, oncall_rotation): value "volunteer-based with weekly signup"
   - `@overlay/project/on-call-rotation`: "On-Call Rotation: Volunteer-Based Weekly Signup" / "on-call rotation"
46. `meme-nofiller/pl_028/3#17` (point 3, rule, commute_duration): value "20 min"
   - `@overlay/transit/commute-duration`: "User Commute Duration: 10 Minutes" / "commute duration"
   - `@overlay/transit/work-commute`: "User Commute: Subway and Bus Transfer to Work" / "work commute"
   - `@overlay/work/caeltura-systems`: "- The user commutes to work by subway and bus transfer ([[transit/work-commute]])."
47. `meme-nofiller/sw_035/4#7` (point end, plain, meeting_day): value "every monday 11am"
   - `@overlay/project/team-meeting`: "Team Meeting Schedule" / "team meeting"
   - `@overlay/project/standup-format`: "The team's standup format is Monday and Thursday synchronous, and asynchronous for the rest of the week." / "- The team's standup format is Monday/Thursday synchronous, and asynchronous for the rest of the week."
48. `meme-nofiller/sw_049/3#7` (point end, plain, error_log): value "certificateverificationerror: certificate chain validation failed for crysthene-db-primary.internal. subject cn does not match expected hostname; chain depth 2 unverified. observed at 2024-07-22t11:09:47z by tls_handshake_listener. rotate the cert via cryptara vault and restart the connection pool to recover"
   - `@overlay/ops/crysthene-db-cert-error`: "Certificate Verification Error: crysthene-db-primary.internal" / "CertificateVerificationError"
   - `@overlay/ops/on-call-rotation`: "- Operational coverage and incident response duties rotate among team members every two weeks." / "- Governs responsibilities for handling operational incidents and service issues like [[ops/crysthene-db-cert-error]]."
   - `@overlay/project/onboarding-guide`: "internal onboarding" / "docs.aurora.internal/onboarding"
49. `meme-nofiller/sw_025/2#3` (point end, plain, sprint_deadline): value "2025 june 20"
   - `@overlay/project/sprint-deadline-2025-06-06 (inactive)`: "[INACTIVE] Project Sprint Deadline: June 6, 2025" / "sprint deadline"
   - `@overlay/project/sprint-deadline-2025-06-20`: "Project Sprint Deadline: June 20, 2025" / "sprint deadline"
   - `@overlay/project/sprint-deadline (inactive)`: "[INACTIVE] Project Sprint Deadline: March 28, 2025" / "sprint deadline"
   - `@overlay/project/release-cadence`: "Release Cadence: Sprint-End Releases Every 2 Weeks" / "sprint release schedule"
50. `meme-nofiller/sw_002/3#11` (point end, plain, error_log): value "segmentationfault at 0x00007fff5a3b2c40 in vorathis_query_planner.so. backtrace: frame 0 query_optimize, frame 1 plan_join, frame 2 execute_select. core dump saved to /var/crash/core.aurora.18923 on 2024-06-12t03:55:09z. last known good build was commit 7a4f9e2; bisect against recent migrations"
   - `@overlay/aurora/error-log-vorathis`: "Aurora Error Log - SegmentationFault in vorathis_query_planner.so" / "vorathis_query_planner.so crash"
   - `@overlay/aurora/ci-config`: "Aurora CI Config - orinthal-build.yml" / "Aurora CI config"
   - `@overlay/aurora/code-review-policy`: "Aurora Code Review Policy - Lead Approval for Core" / "core directory reviews"
   - `@overlay/aurora/deploy-command`: "Aurora Deploy Command - orinthal publish --tier production" / "Aurora deploy command"
   - `@overlay/aurora/design-system`: "Aurora Design System - Synthari Elements v1.2" / "Aurora design system"
   - `@overlay/aurora/dockerfile`: "Aurora Dockerfile - deploy/Dockerfile.korinth" / "Aurora Dockerfile"
   - `@overlay/aurora/log-drain`: "Aurora Log Drain - stream.velturis.io/aurora" / "Aurora log drain"
   - `@overlay/aurora/test-coverage`: "Aurora Test Coverage Target - 90% Core Modules" / "core modules coverage"
   - `@overlay/aurora/cloud-deployment (inactive)`: "[INACTIVE] Aurora Cloud Deployment - Narvex Cloud" / "Aurora cloud deployment"
   - `@overlay/aurora/cloud-deployment-thandrel`: "Aurora Cloud Deployment - Thandrel Infra" / "Aurora cloud deployment"

