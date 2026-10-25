# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/prestomation/Pawsistant/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                            |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------ | -------: | -------: | -------: | -------: | ------: | --------: |
| custom\_components/pawsistant/\_\_init\_\_.py   |      618 |      193 |      212 |       51 |     63% |36-43, 222, 247-\>246, 283, 301, 354-355, 359-\>exit, 365, 372-380, 386-396, 448-500, 536-\>545, 561-\>559, 563, 577, 585, 593, 604-618, 622-624, 637-638, 647-649, 672, 699, 725, 739-740, 751-752, 760-762, 769, 783-786, 812-815, 846-847, 904, 914, 943, 954, 962, 971, 977, 995-\>999, 1020, 1043, 1048, 1054, 1056, 1061, 1066, 1074, 1082-1083, 1092-1094, 1101, 1118-1146, 1170, 1182, 1201-1203, 1225-1226, 1228-1229, 1236, 1242, 1265-1268, 1289-1313, 1317-1334, 1338-1340, 1344-1346, 1400-1410, 1418, 1431-\>1450 |
| custom\_components/pawsistant/care\_link.py     |      221 |       32 |       74 |        8 |     84% |120-121, 197, 212-213, 250-254, 265-273, 390-391, 418, 436-\>430, 450, 458-459, 470, 479, 572-574, 584-587 |
| custom\_components/pawsistant/config\_flow.py   |      372 |       50 |      170 |       37 |     82% |108, 126, 165-166, 353-\>355, 357, 360, 386, 396, 402-414, 426, 446, 463, 474, 481, 483, 484-\>491, 487-\>489, 517-518, 534, 549-552, 568, 574-\>596, 581, 637, 673-\>675, 722, 740, 742, 744, 749, 753, 757, 761, 763, 767, 769-\>806, 780, 791-792, 799-\>802, 809 |
| custom\_components/pawsistant/const.py          |       19 |        0 |        0 |        0 |    100% |           |
| custom\_components/pawsistant/coordinator.py    |       47 |        6 |        4 |        0 |     88% |39-40, 81-82, 90-91 |
| custom\_components/pawsistant/diagnostics.py    |       85 |       31 |       18 |        5 |     61% |51-53, 65-70, 106-132, 156-157, 165, 170-\>169 |
| custom\_components/pawsistant/import\_export.py |      453 |       60 |      208 |       38 |     85% |90, 127-\>126, 285-286, 292-293, 299-300, 317-318, 346-347, 356-357, 359, 362-363, 366-367, 440, 445, 457-\>454, 463-464, 494, 507, 509-510, 513, 521, 540-541, 547-552, 556-557, 558-\>564, 560-561, 571-576, 582-587, 595-\>602, 631-632, 651-654, 666-671, 680-681, 687-688, 715-716, 736, 738-739, 763-767, 783-\>785 |
| custom\_components/pawsistant/sensor.py         |      230 |        6 |       62 |        4 |     97% |109-110, 117-118, 186, 332, 508-\>510, 510-\>512 |
| custom\_components/pawsistant/store.py          |      451 |       92 |      200 |       31 |     76% |167, 184-225, 241-\>253, 261, 302, 303-\>299, 367, 388, 447, 458-459, 474-479, 483-486, 549, 560, 587-\>586, 604, 651-\>650, 667-686, 700-\>697, 705, 738, 749, 785-788, 790-793, 796, 810, 815-\>801, 828-\>831, 857-860, 865, 975-978, 982-984, 986-988, 996-1002, 1004-\>1033, 1015-1020, 1047-1048 |
| custom\_components/pawsistant/supplies.py       |      135 |        0 |       60 |        0 |    100% |           |
| custom\_components/pawsistant/supply\_link.py   |       94 |       72 |       40 |        1 |     17% |36-45, 50-51, 56, 61-68, 78-89, 102-108, 123-138, 143-145, 156-163, 174-179, 184-186, 196-203 |
| **TOTAL**                                       | **2725** |  **542** | **1048** |  **175** | **77%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/prestomation/Pawsistant/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/prestomation/Pawsistant/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prestomation/Pawsistant/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/prestomation/Pawsistant/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fprestomation%2FPawsistant%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/prestomation/Pawsistant/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.