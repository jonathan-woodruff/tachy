import anvil.email
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server
from . import DataHandling
from datetime import *
from pulp import *
import math
import anvil.tz
import anvil.http

#returns the nurses FTE in numeric, decimal form
def get_fte(fteStr):
  if fteStr == 'FTE (1.0)':
    fte = 1.0
  elif fteStr == 'FTE (0.9)':
    fte = 0.9
  elif fteStr == 'FTE (0.8)':
    fte = 0.8
  elif fteStr == 'FTE (0.7)':
    fte = 0.7
  elif fteStr == 'FTE (0.6)':
    fte = 0.6
  elif fteStr == 'FTE (0.5)':
    fte = 0.5
  elif fteStr == 'FTE (0.4)':
    fte = 0.4
  elif fteStr == 'FTE (0.3)':
    fte = 0.3
  elif fteStr == 'FTE (0.2)':
    fte = 0.2
  elif fteStr == 'FTE (0.1)':
    fte = 0.1
  return fte

#returns an error message if there are user entries that will predictably cause the model to be infeasible
def check_for_feasibility_issues(scheduleID):
  #A nurse on any given day can only be assigned exactly one of PTO, PAT, ACLS, Off. Also cannot have a holiday on those days. If, for example, a nurse requested off and has PTO on the same day, then the model will be infeasible
  namesAndDates = []
  #A nurse cannot be assigned PAT, ACLS, PTO, or Off on a holiday.
  holidays = []
  for h in app_tables.holidays.search(schedule_id = scheduleID):
    holidays.append(h['holiday'])
  for ptoRow in app_tables.pto.search(schedule_id = scheduleID):
    nurseName = ptoRow['nurse_name']
    ptoDate = ptoRow['pto_date']
    dateDisplay = ptoRow['pto_date_display']
    if ptoDate in holidays:
      return nurseName + ' cannot be assigned PTO on ' + dateDisplay + ' because it is a holiday'
    namesAndDates.append([nurseName,dateDisplay])
    userID = ptoRow['user_id']
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    startDate = rosterRow['start_date']
    if startDate not in ('',None):
      startDateDisplay = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
      if ptoDate < startDate:
        return nurseName + ' cannot be assigned PTO prior to their start date which is ' + startDateDisplay
  for patRow in app_tables.pat.search(schedule_id = scheduleID):
    nurseName = patRow['nurse_name']
    patDate = patRow['pat_date']
    dateDisplay = patRow['pat_date_display']
    if patDate in holidays:
      return nurseName + ' cannot be assigned PAT on ' + dateDisplay + ' because it is a holiday'
    namesAndDates.append([nurseName,dateDisplay])
    userID = patRow['user_id']
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    startDate = rosterRow['start_date']
    if startDate not in ('',None):
      startDateDisplay = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
      if patDate < startDate:
        return nurseName + ' cannot be assigned PAT prior to their start date which is ' + startDateDisplay
  for aclsRow in app_tables.acls.search(schedule_id = scheduleID):
    nurseName = aclsRow['nurse_name']
    aclsDate = aclsRow['acls_date']
    dateDisplay = aclsRow['acls_date_display']
    if aclsDate in holidays:
      return nurseName + ' cannot be assigned ACLS on ' + dateDisplay + ' because it is a holiday'
    namesAndDates.append([nurseName,dateDisplay])
    userID = aclsRow['user_id']
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    startDate = rosterRow['start_date']
    if startDate not in ('',None):
      startDateDisplay = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
      if aclsDate < startDate:
        return nurseName + ' cannot be assigned ACLS prior to their start date which is ' + startDateDisplay
  for offRow in app_tables.off.search(schedule_id = scheduleID):
    nurseName = offRow['nurse_name']
    offDate = offRow['off_date']
    dateDisplay = offRow['off_date_display']
    if offDate in holidays:
      return nurseName + ' cannot request off ' + dateDisplay + ' because it is a holiday'
    namesAndDates.append([nurseName,dateDisplay])
    userID = offRow['user_id']
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    startDate = rosterRow['start_date']
    if startDate not in ('',None):
      startDateDisplay = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
      if offDate < startDate:
        return nurseName + ' cannot request off a day that is prior to their start date which is ' + startDateDisplay
  info = DataHandling.is_duplicates(namesAndDates)
  isDuplicates = info[0]
  if isDuplicates: 
    duplicateItem = info[1]
    duplicateName = duplicateItem[0]
    duplicateDateDisplay = duplicateItem[1]
    return duplicateName + ' can at most be assigned one of PTO, Request Off, PAT, ACLS on ' + duplicateDateDisplay
  #OPT nurses cannot request to work on a holiday
  for optRow in app_tables.opt.search(schedule_id = scheduleID):
    nurseName = optRow['nurse_name']
    optDate = optRow['opt_date']
    dateDisplay = optRow['opt_date_display']
    if optDate in holidays:
      return nurseName + ' cannot request to work on ' + dateDisplay + ' because it is a holiday'
  #Check if a nurse was assigned more PTO and holidays than their FTE allows in any given pay period
  scheduleStartDate = DataHandling.get_first_day(scheduleID)
  for r in app_tables.roster.search(schedule_id = scheduleID):
    fteStr = r['fte']
    nurseName = r['nurse_name']
    if 'FTE' in fteStr:
      userID = r['user_id']
      fte = get_fte(fteStr)
      maxDays = fte * 10
      numHolidaysPP1 = 0
      numPTOPP1 = 0
      numHolidaysPP2 = 0
      numPTOPP2 = 0
      numHolidaysPP3 = 0
      numPTOPP3 = 0
      for ptoRow in app_tables.pto.search(schedule_id = scheduleID, user_id = userID):
        ptoDate = ptoRow['pto_date']
        if ptoDate < scheduleStartDate + timedelta(days = 14):
          numPTOPP1 += 1
        elif ptoDate < scheduleStartDate + timedelta(days = 28):
          numPTOPP2 += 1
        elif ptoDate < scheduleStartDate + timedelta(days = 42):
          numPTOPP3 += 1
      for hRow in app_tables.holidays.search(schedule_id = scheduleID):
        hDate = hRow['holiday']
        if hDate < scheduleStartDate + timedelta(days = 14):
          numHolidaysPP1 += 1
        elif hDate < scheduleStartDate + timedelta(days = 28):
          numHolidaysPP2 += 1
        elif hDate < scheduleStartDate + timedelta(days = 42):
          numHolidaysPP3 += 1
      if numPTOPP1 + numHolidaysPP1 > maxDays:
        return nurseName + ' cannot be assigned more than ' + str(int(maxDays)) + ' PTO and holidays in the first pay period because ' + nurseName + ' is ' + fteStr + '.'
      elif numPTOPP2 + numHolidaysPP2 > maxDays:
        return nurseName + ' cannot be assigned more than ' + str(int(maxDays)) + ' PTO and holidays in the second pay period because ' + nurseName + ' is ' + fteStr + '.'
      elif numPTOPP3 + numHolidaysPP3 > maxDays:
        return nurseName + ' cannot be assigned more than ' + str(int(maxDays)) + ' PTO and holidays in the third pay period because ' + nurseName + ' is ' + fteStr + '.'
  #Check for issues with the number of days each nurse requested off in each pay period
  #Also record the number of early/backup late/late shifts each nurse is available to work in each pay period so you can check for feasibility issues a bit further down
  nurseShiftsAvailable = {} #e.g. nurseShiftsAvailable['Carissa'] == [[5, 3, 6],[6, 4, 8], [9, 4, 8]] where [5,3,6] is for the first pay period, 5 is the number of early shifts Carissa can work that pp, 3 the number of backup late, 6 the number of late
  for r in app_tables.roster.search(schedule_id = scheduleID,fte = q.like('FTE (%')):
    fte = get_fte(r['fte'])
    userID = r['user_id']
    nurseName = r['nurse_name']
    maxReqOffPP = 10 - (fte * 10) #the max number of days a nurse can request off in a given pay period
    ##initialize number of requests off for each pay period
    numReqPP1 = 0
    numReqPP2 = 0
    numReqPP3 = 0
    ##initialize whether the user requested off the first friday of each pay period
    isReqFirstFridayPP1 = False
    isReqFirstFridayPP2 = False
    isReqFirstFridayPP3 = False
    ##initialize number of requests off for each workweek (workweeks in this case do not include the first friday of the pay period)
    numReqWW1 = 0
    numReqWW2 = 0
    numReqWW3 = 0
    numReqWW4 = 0
    numReqWW5 = 0
    numReqWW6 = 0
    for offRow in app_tables.off.search(schedule_id = scheduleID, user_id = userID):
      offDate = offRow['off_date']
      if scheduleStartDate == offDate:
        isReqFirstFridayPP1 = True
        numReqPP1 += 1
      elif scheduleStartDate + timedelta(days = 3) <= offDate <= scheduleStartDate + timedelta(days = 7):
        numReqWW1 += 1
        numReqPP1 += 1
      elif scheduleStartDate + timedelta(days = 10) <= offDate <= scheduleStartDate + timedelta(days = 13):
        numReqWW2 += 1
        numReqPP1 += 1
      elif scheduleStartDate + timedelta(days = 14) == offDate:
        isReqFirstFridayPP2 = True
        numReqPP2 += 1
      elif scheduleStartDate + timedelta(days = 17) <= offDate <= scheduleStartDate + timedelta(days = 21):
        numReqWW3 += 1
        numReqPP2 += 1
      elif scheduleStartDate + timedelta(days = 24) <= offDate <= scheduleStartDate + timedelta(days = 27):
        numReqWW4 += 1
        numReqPP2 += 1
      elif scheduleStartDate + timedelta(days = 28) == offDate:
        isReqFirstFridayPP3 = True
        numReqPP3 += 1
      elif scheduleStartDate + timedelta(days = 31) <= offDate <= scheduleStartDate + timedelta(days = 35):
        numReqWW5 += 1
        numReqPP3 ++ 1
      elif scheduleStartDate + timedelta(days = 38) <= offDate <= scheduleStartDate + timedelta(days = 41):
        numReqWW6 += 1
        numReqPP3 += 1
    ##Check if the nurse has more days she requested off than her FTE allows in any of the pay periods
    if numReqPP1 > maxReqOffPP:
      return nurseName + ' cannot request more than ' + str(int(maxReqOffPP)) + ' days off during the first pay period'
    if numReqPP2 > maxReqOffPP:
        return nurseName + ' cannot request more than ' + str(int(maxReqOffPP)) + ' days off during the second pay period'
    if numReqPP3 > maxReqOffPP:
        return nurseName + ' cannot request more than ' + str(int(maxReqOffPP)) + ' days off during the third pay period'
    ##Check if the configuration of the days the nurse requested off is such that it will cause unbalanced workweeks (e.g. a 0.8 nurse requests both days off in the second workweek, forcing her to have to work 5 days the first workweek which is not allowed)
    if fte == 0.8 and isReqFirstFridayPP1 and numReqWW2 == 1:
      return nurseName + ' cannot request off the first Friday of the first pay period and another day in the last Mon-Thu of the first pay period because it forces them to work all five days the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.8 and numReqWW2 == 2:
      return nurseName + ' cannot request off two days in the last Mon-Thu of the first pay period because it forces them to work all five days the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.8 and isReqFirstFridayPP2 and numReqWW4 == 1:
      return nurseName + ' cannot request off the first Friday of the second pay period and another day in the last Mon-Thu of the second pay period because it forces them to work all five days the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.8 and numReqWW4 == 2:
      return nurseName + ' cannot request off two days in the last Mon-Thu of the second pay period because it forces them to work all five days the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.8 and isReqFirstFridayPP3 and numReqWW6 == 1:
      return nurseName + ' cannot request off the first Friday of the third pay period and another day in the last Mon-Thu of the third pay period because it forces them to work all five days the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.8 and numReqWW6 == 2:
      return nurseName + ' cannot request off two days in the last Mon-Thu of the third pay period because it forces them to work all five days the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.7 and isReqFirstFridayPP1 and numReqWW2 == 2:
      return nurseName + ' cannot request off the first Friday of the first pay period and the last Mon-Thu of the first pay period because it forces them to work all five days the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.7 and numReqWW2 == 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the first pay period because it forces them to work all five days of the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.7 and isReqFirstFridayPP2 and numReqWW4 == 2:
      return nurseName + ' cannot request off the first Friday of the second pay period and the last Mon-Thu of the second pay period because it forces them to work all five days the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.7 and numReqWW4 == 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the second pay period because it forces them to work all five days of the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.7 and isReqFirstFridayPP3 and numReqWW6 == 2:
      return nurseName + ' cannot request off the first Friday of the third pay period and the last Mon-Thu of the third pay period because it forces them to work all five days the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.7 and numReqWW6 == 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the third pay period because it forces them to work all five days of the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.6 and isReqFirstFridayPP1 and numReqWW2 >= 2:
      return nurseName + ' cannot request off the first Friday of the first pay period and two or more of the last Mon-Thu in the first pay period because it forces them to work four days the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.6 and numReqWW2 >= 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the first pay period because it forces them to work four days in the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.6 and numReqWW1 == 4:
      return nurseName + ' cannot request off four days in the first full Mon-Fri workweek of the first pay period because it forces them to work all four days of the last Mon-Thu workweek of the first pay period'
    elif fte == 0.6 and isReqFirstFridayPP1 and numReqWW1 == 3:
      return nurseName + ' cannot request off the first Friday of the first pay period and three days of the first full Mon-Fri workweek of the first pay period because it forces them to work all four days of the last Mon-Thu workweek of the first pay period'
    elif fte == 0.6 and isReqFirstFridayPP2 and numReqWW4 >= 2:
      return nurseName + ' cannot request off the first Friday of the second pay period and two or more of the last Mon-Thu in the second pay period because it forces them to work four days the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.6 and numReqWW4 >= 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the second pay period because it forces them to work four days in the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.6 and numReqWW3 == 4:
      return nurseName + ' cannot request off four days in the first full Mon-Fri workweek of the second pay period because it forces them to work all four days of the last Mon-Thu workweek of the second pay period'
    elif fte == 0.6 and isReqFirstFridayPP2 and numReqWW3 == 3:
      return nurseName + ' cannot request off the first Friday of the second pay period and three days of the first full Mon-Fri workweek of the second pay period because it forces them to work all four days of the last Mon-Thu workweek of the second pay period'
    elif fte == 0.6 and isReqFirstFridayPP3 and numReqWW6 >= 2:
      return nurseName + ' cannot request off the first Friday of the third pay period and two or more of the last Mon-Thu in the third pay period because it forces them to work four days the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.6 and numReqWW6 >= 3:
      return nurseName + ' cannot request off three days in the last Mon-Thu of the third pay period because it forces them to work four days in the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.6 and numReqWW5 == 4:
      return nurseName + ' cannot request off four days in the first full Mon-Fri workweek of the third pay period because it forces them to work all four days of the last Mon-Thu workweek of the third pay period'
    elif fte == 0.6 and isReqFirstFridayPP3 and numReqWW5 == 3:
      return nurseName + ' cannot request off the first Friday of the third pay period and three days of the first full Mon-Fri workweek of the third pay period because it forces them to work all four days of the last Mon-Thu workweek of the third pay period'
    elif fte == 0.5 and isReqFirstFridayPP1 and numReqWW2 >= 3:
      return nurseName + ' cannot request off the first Friday of the first pay period and three or more days of the last Mon-Thu workweek of the first pay period because it forces them to work four days in the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.5 and numReqWW2 == 4:
      return nurseName + ' cannot request off the last four days of the first pay period because it forces them to work four days in the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.5 and numReqWW1 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek in the first pay period because it forces them to work all four days in the last Mon-Thu workweek of the first pay period'
    elif fte == 0.5 and isReqFirstFridayPP1 and numReqWW1 == 4:
      return nurseName + ' cannot request off the first Friday of the first pay period and four days in the first full Mon-Fri workweek of the first pay period because it forces them to work four days in the last Mon-Thu workweek of the first pay period'
    elif fte == 0.5 and isReqFirstFridayPP2 and numReqWW4 >= 3:
      return nurseName + ' cannot request off the first Friday of the second pay period and three or more days of the last Mon-Thu workweek of the second pay period because it forces them to work four days in the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.5 and numReqWW4 == 4:
      return nurseName + ' cannot request off the last four days of the second pay period because it forces them to work four days in the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.5 and numReqWW3 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek in the second pay period because it forces them to work all four days in the last Mon-Thu workweek of the second pay period'
    elif fte == 0.5 and isReqFirstFridayPP2 and numReqWW3 == 4:
      return nurseName + ' cannot request off the first Friday of the second pay period and four days in the first full Mon-Fri workweek of the second pay period because it forces them to work four days in the last Mon-Thu workweek of the second pay period'
    elif fte == 0.5 and isReqFirstFridayPP3 and numReqWW6 >= 3:
      return nurseName + ' cannot request off the first Friday of the third pay period and three or more days of the last Mon-Thu workweek of the third pay period because it forces them to work four days in the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.5 and numReqWW6 == 4:
      return nurseName + ' cannot request off the last four days of the third pay period because it forces them to work four days in the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.5 and numReqWW5 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek in the third pay period because it forces them to work all four days in the last Mon-Thu workweek of the third pay period'
    elif fte == 0.5 and isReqFirstFridayPP3 and numReqWW5 == 4:
      return nurseName + ' cannot request off the first Friday of the third pay period and four days in the first full Mon-Fri workweek of the third pay period because it forces them to work four days in the last Mon-Thu workweek of the third pay period'
    elif fte == 0.4 and isReqFirstFridayPP1 and numReqWW2 >= 3:
      return nurseName + ' cannot request off the first Friday of the first pay period and three or more days of the last Mon-Thu workweek of the first pay period because it forces them to work three days in the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.4 and numReqWW2 == 4:
      return nurseName + ' cannot request off the last four days of the first pay period because it forces them to work three days in the first full Mon-Fri workweek of the first pay period'
    elif fte == 0.4 and numReqWW1 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek of the first pay period because it forces them to work three days in the last Mon-Thu workweek of the first pay period'
    elif fte == 0.4 and isReqFirstFridayPP1 and numReqWW1 >= 4:
      return nurseName + ' cannot request off the first Friday of the first pay period and four or more days of the first full Mon-Fri workweek of the first pay period because it forces them to work three days in the last Mon-Thu workweek of the first pay period'
    elif fte == 0.4 and isReqFirstFridayPP2 and numReqWW4 >= 3:
      return nurseName + ' cannot request off the first Friday of the second pay period and three or more days of the last Mon-Thu workweek of the second pay period because it forces them to work three days in the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.4 and numReqWW4 == 4:
      return nurseName + ' cannot request off the last four days of the second pay period because it forces them to work three days in the first full Mon-Fri workweek of the second pay period'
    elif fte == 0.4 and numReqWW3 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek of the second pay period because it forces them to work three days in the last Mon-Thu workweek of the second pay period'
    elif fte == 0.4 and isReqFirstFridayPP2 and numReqWW3 >= 4:
      return nurseName + ' cannot request off the first Friday of the second pay period and four or more days of the first full Mon-Fri workweek of the second pay period because it forces them to work three days in the last Mon-Thu workweek of the second pay period'
    elif fte == 0.4 and isReqFirstFridayPP3 and numReqWW6 >= 3:
      return nurseName + ' cannot request off the first Friday of the third pay period and three or more days of the last Mon-Thu workweek of the third pay period because it forces them to work three days in the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.4 and numReqWW6 == 4:
      return nurseName + ' cannot request off the last four days of the third pay period because it forces them to work three days in the first full Mon-Fri workweek of the third pay period'
    elif fte == 0.4 and numReqWW5 == 5:
      return nurseName + ' cannot request off all five days of the first full Mon-Fri workweek of the third pay period because it forces them to work three days in the last Mon-Thu workweek of the third pay period'
    elif fte == 0.4 and isReqFirstFridayPP3 and numReqWW5 >= 4:
      return nurseName + ' cannot request off the first Friday of the third pay period and four or more days of the first full Mon-Fri workweek of the third pay period because it forces them to work three days in the last Mon-Thu workweek of the third pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP1 and numReqWW2 == 4:
      return nurseName + ' cannot request off the first Friday of the first pay period and all four days of the last Mon-Thu workweek of the first pay period because it forces them to work too many days the first full Mon-Fri workweek of the first pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP1 and numReqWW1 == 5:
      return nurseName + ' cannot request off the first Friday of the first pay period and all five days of the first full Mon-Fri workweek of the first pay period because it forces them to work too many days in the last Mon-Thu workweek of the first pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP2 and numReqWW4 == 4:
      return nurseName + ' cannot request off the first Friday of the second pay period and all four days of the last Mon-Thu workweek of the second pay period because it forces them to work too many days the first full Mon-Fri workweek of the second pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP2 and numReqWW3 == 5:
      return nurseName + ' cannot request off the first Friday of the second pay period and all five days of the first full Mon-Fri workweek of the second pay period because it forces them to work too many days in the last Mon-Thu workweek of the second pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP3 and numReqWW6 == 4:
      return nurseName + ' cannot request off the first Friday of the third pay period and all four days of the last Mon-Thu workweek of the third pay period because it forces them to work too many days the first full Mon-Fri workweek of the third pay period'
    elif fte in (0.3, 0.2) and isReqFirstFridayPP3 and numReqWW5 == 5:
      return nurseName + ' cannot request off the first Friday of the third pay period and all five days of the first full Mon-Fri workweek of the third pay period because it forces them to work too many days in the last Mon-Thu workweek of the third pay period'
  return ''
  
def get_user_input(scheduleID):
  #####get schedule start date to create calendar#####
  scheduleStartDate = DataHandling.get_first_day(scheduleID)
  calendar = []
  nextDay = scheduleStartDate
  for i in range(42):
    calendar.append(nextDay)
    nextDay += timedelta(days = 1)
  
  numDays = len(calendar)
  
  #####organize rninfo table into the nurses list#####
  nurses = []
  for row in app_tables.roster.search(schedule_id = scheduleID):
    fte = row['fte']
    if fte != 'CNA':
      nurse = row['nurse_name']
      if 'FTE' in fte:
        fte = get_fte(fte)
      sd = row['start_date'] #date
      sd = DataHandling.get_calendar_index(sd, calendar, numDays) #calendar index
      if sd == None:
        sd = 0
      isCharge = row['charge_tf']
      nurses.append([nurse, fte, sd, isCharge])
  
  numNurses = len(nurses)
  
  #####organize holidays table into the holidays list#####
  holidays = []
  for row in app_tables.holidays.search(schedule_id = scheduleID):
    hDate = row['holiday']
    holidays.append(DataHandling.get_calendar_index(hDate, calendar, numDays))
  
  #####organize pto table into the pto list#####
  pto = []
  for row in app_tables.pto.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    ptoDate = row['pto_date']
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(ptoDate, calendar, numDays)
    if ci not in holidays:
      pto.append([ni, ci])
  
  #####organize the off table into the off list#####
  off = []
  for row in app_tables.off.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    offDate = row['off_date']
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(offDate, calendar, numDays)
    off.append([ni, ci])
  
  #####organize the shiftOff table into the shiftOff list#####
  shiftOff = []
  for row in app_tables.shiftsunavailable.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    shiftOffDate = row['date']
    shiftString = row['shift']
    shift = -1
    chargeShift = -1
    if shiftString == "Shift 6":
      shift = 0
      chargeShift = 5
    elif shiftString == "Shift 7":
      shift = 1
      chargeShift = 6
    elif shiftString == "Shift 8":
      shift = 2
      chargeShift = 7
    elif shiftString == "Shift 7*":
      shift = 4
      chargeShift = 8
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(shiftOffDate, calendar, numDays)
    shiftOff.append([ni, ci, shift])
    shiftOff.append([ni, ci, chargeShift])
  
  #####organize the pat table into the patShifts list#####
  patShifts = []
  for row in app_tables.pat.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    patDate = row['pat_date']
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(patDate, calendar, numDays)
    patShifts.append([ni, ci])
  
  #####organize the opt table into the opt list#####
  optShifts = []
  for row in app_tables.opt.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    optDate = row['opt_date']
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(optDate, calendar, numDays)
    optShifts.append([ni, ci])
  
  #####organize the acls table into the aclsShifts list#####
  aclsShifts = []
  for row in app_tables.acls.search(schedule_id = scheduleID,included_in_roster_tf = True):
    nurseName = row['nurse_name']
    aclsDate = row['acls_date']
    ni = DataHandling.get_nurse_index(nurseName, nurses, numNurses)
    ci = DataHandling.get_calendar_index(aclsDate, calendar, numDays)
    aclsShifts.append([ni, ci])
  
  #####organize the demand table into the demand list
  dailyDemand = []
  for i in range(numDays):
    dailyDemand.append(0)
  for row in app_tables.demand.search(schedule_id = scheduleID):
    date = row['demand_date']
    numDemand = row['demand']
    if numDemand in ('',None):
      numDemand = 0
    else:
      numDemand = int(numDemand)
    ci = DataHandling.get_calendar_index(date, calendar, numDays)
    dailyDemand[ci] = numDemand

  return [numNurses,numDays,nurses,scheduleStartDate,calendar,holidays,pto,off,shiftOff,patShifts,optShifts,aclsShifts,dailyDemand]

#Sort based on index 0
def sorting_index_0(element):
  return element[0]
  
#Sort based on index 1
def sorting_index_1(element):
  return element[1]

def process_user_input(userInput):
  #itemize user input
  numNurses = userInput[0]
  numDays = userInput[1]
  nurses = userInput[2]
  scheduleStartDate = userInput[3]
  calendar = userInput[4]
  holidays = userInput[5]
  pto = userInput[6]
  off = userInput[7]
  shiftOff = userInput[8]
  patShifts = userInput[9]
  optShifts = userInput[10]
  aclsShifts = userInput[11]
  dailyDemand = userInput[12]

  #assign the number of shifts
  ## 0 -> early
  ## 1 -> middle 
  ## 2 -> late
  ## 3 -> PAT
  ## 4 -> backup late
  ## 5 -> early & charge 
  ## 6 -> middle & charge
  ## 7 -> late & charge
  ## 8 -> backup late & charge
  ## 9 -> ACLS
  ## 10 -> PTO
  ## 11 -> OFF
  numShifts = 12

  #chargeNurses is a list of charge nurses (nurses indices)
  chargeNurses = []
  for k in range(numNurses):
    if nurses[k][3]:
      chargeNurses.append(k)

  chargeNursesLength = len(chargeNurses)
    
  #fteNurses is a list of FTE nurses (nurses indices)
  #optNurses is a list of OPT nurses (nurse indices)
  fteNurses = []
  optNurses = []
  for k in range(numNurses):
    if nurses[k][1] == 'OPT':
      optNurses.append(k)
    else:
      fteNurses.append(k)

  fteNursesLength = len(fteNurses)

  #allMondays is a list of mondays (calendar indices)
  #allFridays is a list of fridays (calendar indices)
  #allMondaysAndFridays is a list of mondays and fridays (calendar indices)
  allMondays = []
  allFridays = []
  allMondaysAndFridays = []
  for i in range(numDays):
    if calendar[i].weekday() == 0:
      allMondaysAndFridays.append(i)
      allMondays.append(i)
    elif calendar[i].weekday() == 4:
      allFridays.append(i)
      allMondaysAndFridays.append(i)

  #holidaysPP is a list of holidays (calendar indices) in a given pay period
  h1 = 0
  h2 = 0
  h3 = 0
  numHolidays = len(holidays)
  for h in range(numHolidays):
    holidayIndex = holidays[h]
    if holidayIndex < 14:
      h1 += 1
    elif holidayIndex < 28:
      h2 += 1
    else:
      h3 += 1
  holidaysPP = [h1, h2, h3]
  
  #weekdaysNotHolidays is a list of calendar indices that are weekdays and not holidays (the days that RNs work)
  weekdaysNotHolidays = []
  for i in range(numDays):
    d = calendar[i]
    if d.weekday() >= 0 and d.weekday() <= 4 and i not in holidays:
      weekdaysNotHolidays.append(i)

  #ptoPP[pp][k] indicates the number of PTO days for nurse k in pay period pp
  #offPP[pp][k] indicates the number of OFF days for nurse k in pay period pp
  ptoPP = []
  offPP = []
  ptoLength = len(pto)
  offLength = len(off)
  for pp in range(3): #for each pay period
    ptoPP.append([])
    offPP.append([])
    for k in range(numNurses):
      ptoPP[pp].append(0)
      offPP[pp].append(0)
  for p in pto:
    nurseIndex = p[0]
    calendarIndex = p[1]
    if calendarIndex < 14:
      ptoPP[0][nurseIndex] += 1
    elif calendarIndex < 28:
      ptoPP[1][nurseIndex] += 1
    elif calendarIndex < 42:
      ptoPP[2][nurseIndex] += 1
  for f in off:
    nurseIndex = f[0]
    calendarIndex = f[1]
    if calendarIndex < 14:
      offPP[0][nurseIndex] += 1
    elif calendarIndex < 28:
      offPP[1][nurseIndex] += 1
    elif calendarIndex < 42:
      offPP[2][nurseIndex] += 1

  #firstMonday is the calendar index of the first Monday of the scheduling period
  firstMonday = 3

  #numHolidaysF is the number of holidays that land on a Friday
  #numHolidaysMF is the number of holidays that land on a Monday or Friday
  numHolidaysF = 0
  numHolidaysMF = 0
  for h in holidays:
    hDate = calendar[h]
    hDayOfWeek = hDate.weekday()
    if hDayOfWeek == 4:
      numHolidaysMF += 1
      numHolidaysF += 1
    elif hDayOfWeek == 0:
      numHolidaysMF += 1
      
  aclsShiftsLength = len(aclsShifts)
  patShiftsLength = len(patShifts)
  shiftOffLength = len(shiftOff)

  #effectiveFte[k] is nurse k's FTE based on the early/middle/late/backup late shifts she can work. 
  ##For example, if the nurse's FTE is 0.8 but she has 5 days of PTO, her effectiveFte is 0.63 because 
  ##there's 5 days she can't work an early/middle/late/backup late shift.
  #effectivePayPeriods is the effective number of pay periods the nurse is working. 
  ##It could be 3, or it could be less if she has some holidays/PAT/ACLS/etc.
  effectiveFte = []
  effectivePayPeriods = []
  earlyCanWork = [] #earlyCanWork[k] = [5, 4, 6] means nurse k is available to work 5 early shifts in the first pay period, etc.
  backupCanWork = []
  lateCanWork = []
  for k in range(numNurses):
    if k in fteNurses:
      #Calculate the nurse's total amount of PTO
      totalPTO = 0
      totalPTOPP1 = 0
      totalPTOPP2 = 0
      totalPTOPP3 = 0
      for p in range(ptoLength):
        nurse = pto[p][0]
        d = pto[p][1]
        if k == nurse:
          totalPTO += 1
          if 0 <= d < 14:
            totalPTOPP1 += 1
          elif 14 <= d < 28:
            totalPTOPP2 += 1
          elif 28 <= d < 42:
            totalPTOPP3 += 1
      #The number of holidays in the pay period
      numHolidaysPP1 = holidaysPP[0]
      numHolidaysPP2 = holidaysPP[1]
      numHolidaysPP3 = holidaysPP[2]
      numHolidays = numHolidaysPP1 + numHolidaysPP2 + numHolidaysPP3
      #Calculate the nurse's total amount of ACLS
      totalACLS = 0
      totalACLSPP1 = 0
      totalACLSPP2 = 0
      totalACLSPP3 = 0
      for a in range(aclsShiftsLength):
        nurse = aclsShifts[a][0]
        d = aclsShifts[a][1]
        if k == nurse:
          totalACLS += 1
          if 0 <= d < 14:
            totalACLSPP1 += 1
          elif 14 <= d < 28:
            totalACLSPP2 += 1
          elif 28 <= d < 42:
            totalACLSPP3 += 1
      #Calculate the nurse's total amount of PAT
      totalPAT = 0
      totalPATPP1 = 0
      totalPATPP2 = 0
      totalPATPP3 = 0
      for p in range(patShiftsLength):
        nurse = patShifts[p][0]
        d = patShifts[p][1]
        if k == nurse:
          totalPAT += 1
          if 0 <= d < 14:
            totalPATPP1 += 1
          elif 14 <= d < 28:
            totalPATPP2 += 1
          elif 28 <= d < 42:
            totalPATPP3 += 1
      #Calculate the nurse's total amount of days spent in orientation
      fte = nurses[k][1]
      startDateIndex = nurses[k][2]
      totalTraining = 0
      totalTrainingPP1 = 0
      totalTrainingPP2 = 0
      totalTrainingPP3 = 0
      weeksInTraining = 0
      if startDateIndex > 0 and startDateIndex <= 7:
        weeksInTraining = 1
      elif startDateIndex > 7 and startDateIndex <= 14:
        weeksInTraining = 2
      elif startDateIndex > 14 and startDateIndex <= 21:
        weeksInTraining = 3
      elif startDateIndex > 21 and startDateIndex <= 28:
        weeksInTraining = 4
      elif startDateIndex > 28 and startDateIndex <= 35:
        weeksInTraining = 5
      if fte == 1 or fte == 0.8 or fte == 0.6 or fte == 0.4 or fte == 0.2:
        totalTraining = fte * 5 * weeksInTraining
        if weeksInTraining <= 2:
          totalTrainingPP1 = fte * 5 * weeksInTraining
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining <= 4:
          totalTrainingPP1 = fte * 10
          totalTrainingPP2 = fte * 5 * (weeksInTraining - 2)
          totalTrainingPP3 = 0
        elif weeksInTraining == 5:
          totalTrainingPP1 = fte * 10
          totalTrainingPP2 = fte * 10
          totalTrainingPP2 = fte * 5
      elif fte == 0.9:
        if weeksInTraining == 1:
          totalTraining = 4
          totalTrainingPP1 = 4
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 2:
          totalTraining = 9
          totalTrainingPP1 = 9
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 3:
          totalTraining = 13
          totalTrainingPP1 = 9
          totalTrainingPP2 = 4
          totalTrainingPP3 = 0
        elif weeksInTraining == 4:
          totalTraining = 18
          totalTrainingPP1 = 9
          totalTrainingPP2 = 9
          totalTrainingPP3 = 0
        elif weeksInTraining == 5:
          totalTraining = 22
          totalTrainingPP1 = 9
          totalTrainingPP2 = 9
          totalTrainingPP3 = 4
      elif fte == 0.7:
        if weeksInTraining == 1:
          totalTraining = 3
          totalTrainingPP1 = 3
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 2:
          totalTraining = 7
          totalTrainingPP1 = 7
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 3:
          totalTraining = 10
          totalTrainingPP1 = 7
          totalTrainingPP2 = 3
          totalTrainingPP3 = 0
        elif weeksInTraining == 4:
          totalTraining = 14
          totalTrainingPP1 = 7
          totalTrainingPP2 = 7
          totalTrainingPP3 = 0
        elif (weeksInTraining == 5):
          totalTraining = 17
          totalTrainingPP1 = 7
          totalTrainingPP2 = 7
          totalTrainingPP3 = 3
      elif fte == 0.5:
        if weeksInTraining == 1:
          totalTraining = 2
          totalTrainingPP1 = 2
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 2:
          totalTraining = 5
          totalTrainingPP1 = 5
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 3:
          totalTraining = 7
          totalTrainingPP1 = 5
          totalTrainingPP2 = 2
          totalTrainingPP3 = 0
        elif weeksInTraining == 4:
          totalTraining = 10
          totalTrainingPP1 = 5
          totalTrainingPP2 = 5
          totalTrainingPP3 = 0
        elif weeksInTraining == 5:
          totalTraining = 12
          totalTrainingPP1 = 5
          totalTrainingPP2 = 5
          totalTrainingPP3 = 2
      elif fte == 0.3:
        if weeksInTraining == 1:
          totalTraining = 1
          totalTrainingPP1 = 1
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 2:
          totalTraining = 3
          totalTrainingPP1 = 3
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 3:
          totalTraining = 4
          totalTrainingPP1 = 3
          totalTrainingPP2 = 1
          totalTrainingPP3 = 0
        elif weeksInTraining == 4:
          totalTraining = 6
          totalTrainingPP1 = 3
          totalTrainingPP2 = 3
          totalTrainingPP3 = 0
        elif weeksInTraining == 5:
          totalTraining = 7
          totalTrainingPP1 = 3
          totalTrainingPP2 = 3
          totalTrainingPP3 = 1
      elif fte == 0.1:
        if weeksInTraining == 1:
          totalTraining = 0
          totalTrainingPP1 = 0
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 2:
          totalTraining = 1
          totalTrainingPP1 = 1
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 3:
          totalTraining = 1
          totalTrainingPP1 = 1
          totalTrainingPP2 = 0
          totalTrainingPP3 = 0
        elif weeksInTraining == 4:
          totalTraining = 2
          totalTrainingPP1 = 1
          totalTrainingPP2 = 1
          totalTrainingPP3 = 0
        elif weeksInTraining == 5:
          totalTraining = 2
          totalTrainingPP1 = 1
          totalTrainingPP2 = 1
          totalTrainingPP3 = 0
      #Count the number of early/backup late/late shifts the nurse is unavailable to work for each pay period
      totalEarlyPP1 = 0
      totalBackupPP1 = 0
      totalLatePP1 = 0
      totalEarlyPP2 = 0
      totalBackupPP2 = 0
      totalLatePP2 = 0
      totalEarlyPP3 = 0
      totalBackupPP3 = 0
      totalLatePP3 = 0
      for t in range(shiftOffLength):
        nurse = shiftOff[t][0]
        d = shiftOff[t][1]
        shift = shiftOff[t][2]
        if k == nurse:
          if 0 <= d < 14:
            if shift == 0:
              totalEarlyPP1 += 1
            elif shift == 2:
              totalLatePP1 += 1
            elif shift == 4:
              totalBackupPP1 += 1
          elif 14 <= d < 28:
            if shift == 0:
              totalEarlyPP2 += 1
            elif shift == 2:
              totalLatePP2 += 1
            elif shift == 4:
              totalBackupPP2 += 1
          elif 28 <= d < 42:
            if shift == 0:
              totalEarlyPP3 += 1
            elif shift == 2:
              totalLatePP3 += 1
            elif shift == 4:
              totalBackupPP3 += 1
      totalUnavailable = totalPTO + totalACLS + totalPAT + totalTraining + numHolidays
      effectiveFte.append(((fte * 10 * 3.0) - totalUnavailable) / 3.0 / 10)
      effectivePayPeriods.append(((fte * 10 * 3.0) - totalUnavailable) / (fte * 10.0))
      totalUnavailablePP1 = totalPTOPP1 + totalACLSPP1 + totalPATPP1 + totalTrainingPP1 + numHolidaysPP1
      totalUnavailablePP2 = totalPTOPP2 + totalACLSPP2 + totalPATPP2 + totalTrainingPP2 + numHolidaysPP2
      totalUnavailablePP3 = totalPTOPP3 + totalACLSPP3 + totalPATPP3 + totalTrainingPP3 + numHolidaysPP3
      availableEarlyPP1 = (fte * 10) - (totalUnavailablePP1 + totalEarlyPP1)
      availableBackupPP1 = (fte * 10) - (totalUnavailablePP1 + totalBackupPP1)
      availableLatePP1 = (fte * 10) - (totalUnavailablePP1 + totalLatePP1)
      availableEarlyPP2 = (fte * 10) - (totalUnavailablePP2 + totalEarlyPP2)
      availableBackupPP2 = (fte * 10) - (totalUnavailablePP2 + totalBackupPP2)
      availableLatePP2 = (fte * 10) - (totalUnavailablePP2 + totalLatePP2)
      availableEarlyPP3 = (fte * 10) - (totalUnavailablePP3 + totalEarlyPP3)
      availableBackupPP3 = (fte * 10) - (totalUnavailablePP3 + totalBackupPP3)
      availableLatePP3 = (fte * 10) - (totalUnavailablePP3 + totalLatePP3)
      earlyCanWork.append([availableEarlyPP1,availableEarlyPP2,availableEarlyPP3])
      backupCanWork.append([availableBackupPP1,availableBackupPP2,availableBackupPP3])
      lateCanWork.append([availableLatePP1,availableLatePP2,availableLatePP3])
    else:
      effectiveFte.append(0)
      effectivePayPeriods.append(0)
      earlyCanWork.append([0,0,0])
      backupCanWork.append([0,0,0])
      lateCanWork.append([0,0,0])

  #totalEffectiveFte is the sum of effective FTE over all FTE nurses
  totalEffectiveFte = 0
  for k in fteNurses:
    totalEffectiveFte += effectiveFte[k]

  #earlyLate: list. earlyLate[nurse] = numEarlyLate where numEarlyLate is the max number of early shifts the nurse should work (same for late shifts)
  ##Note the calculations are based on adjusted FTE. If we calculated based on FTE alone, then it wouldn't 
  ##properly account for the situation where a nurse has a ton of PTO/ACLS/Training...things that count toward 
  ##FTE but don't give the opportunity to work early. So FTE needs to be adjusted for PTO/ACLS/Training. Same for late and backup late.
  earlyLate = []
  backupLate = []

  #Calculate the theoretical numEarly, rounded up
  ##The theoretical number of early shifts a nurse should work is effectiveFte / totalEffectiveFte * 60. 
  ##(There are 60 total early shifts in the three week period). Same for late and backup late
  for k in range(numNurses):
    if k in fteNurses:
      effFte = effectiveFte[k]
      numEarlyLate = math.ceil(effFte / totalEffectiveFte * 60.0)
      numBackupLate = math.ceil(effFte / totalEffectiveFte * 30.0)
      earlyLate.append(numEarlyLate)
      backupLate.append(numBackupLate)
    else:
      earlyLate.append(0)
      backupLate.append(0)

  maxEarlyLate = []
  maxBackupLate = []
  for k in range(numNurses):
    if k in fteNurses:
      numPP = effectivePayPeriods[k]
      numEarlyLateShifts = earlyLate[k] #total number of early shifts the nurse should work. same for late shifts
      numEarlyLatePP = math.ceil(numEarlyLateShifts / numPP) #max number of early shifts nurse should work each pay period. same for late shifts
      maxEarlyLate.append(numEarlyLatePP)
      numBackupLateShifts = backupLate[k]
      numBackupLatePP = math.ceil(numBackupLateShifts / numPP)
      maxBackupLate.append(numBackupLatePP)
    else:
      maxEarlyLate.append(0)
      maxBackupLate.append(0)

  #Get a warning message if the nurse checked off too many early/backup late/late shifts in Shifts Unavailabl
  for k in fteNurses:
    numPP = effectivePayPeriods[k]
    numEarlyShifts = earlyLate[k] #total number of early shifts the nurse should work
    numEarlyPP = math.floor(numEarlyShifts / numPP) #likely the min number of early shifts the nurse will need to work each pay period
    numLatePP = numEarlyPP
    numBackupShifts = backupLate[k]
    numBackupPP = math.floor(numBackupShifts / numPP)
    nurseName = nurses[k][0]
    warningMessage = ''
    if earlyCanWork[k][0] < numEarlyPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of early shifts in the first pay period. This could potentially cause issues since the schedule will try to assign a fair number of early shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 6\" boxes in the first pay period.'
    elif earlyCanWork[k][1] < numEarlyPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of early shifts in the second pay period. This could potentially cause issues since the schedule will try to assign a fair number of early shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 6\" boxes in the second pay period.'
    elif earlyCanWork[k][2] < numEarlyPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of early shifts in the third pay period. This could potentially cause issues since the schedule will try to assign a fair number of early shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 6\" boxes in the third pay period.'
    elif backupCanWork[k][0] < numBackupPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of backup late shifts in the first pay period. This could potentially cause issues since the schedule will try to assign a fair number of backup late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 7*\" boxes in the first pay period.'
    elif backupCanWork[k][1] < numBackupPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of backup late shifts in the second pay period. This could potentially cause issues since the schedule will try to assign a fair number of backup late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 7*\" boxes in the second pay period.'
    elif backupCanWork[k][2] < numBackupPP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of backup late shifts in the third pay period. This could potentially cause issues since the schedule will try to assign a fair number of backup late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 7*\" boxes in the third pay period.'
    elif lateCanWork[k][0] < numLatePP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of late shifts in the first pay period. This could potentially cause issues since the schedule will try to assign a fair number of late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 8\" boxes in the first pay period.'
    elif lateCanWork[k][1] < numLatePP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of late shifts in the second pay period. This could potentially cause issues since the schedule will try to assign a fair number of late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 8\" boxes in the second pay period.'
    elif lateCanWork[k][2] < numLatePP:
      warningMessage = nurseName + ' might not be available enough to work a fair number of late shifts in the third pay period. This could potentially cause issues since the schedule will try to assign a fair number of late shifts. If the schedule won\'t generate due to error, look at the Shifts Unavailable table to see if the nurse checked too many \"Can\'t do 8\" boxes in the third pay period.'

  #chargeDist: list containing [nurse numChargeShifts] pairs where numChargeShifts is the max number of charge shifts the nurse should work, adjusted for effective FTE
  chargeDist = []
  chargeDistMin = []
  
  totalEffectiveChargeFte = 0
  for k in chargeNurses:
    totalEffectiveChargeFte += effectiveFte[k]

  for k in chargeNurses:
    effFte = effectiveFte[k]
    numChargeShifts = math.ceil(effFte / totalEffectiveChargeFte * 30)
    numChargeShiftsMin = math.floor(effFte / totalEffectiveChargeFte * 30)
    chargeDist.append([k, numChargeShifts])
    chargeDistMin.append([k, numChargeShiftsMin])
      
  #nonChargeNurses is a list of nurses (nurse indices) who cannot do charge shift
  nonChargeNurses = []
  for n in range(numNurses):
    if n not in chargeNurses:
      nonChargeNurses.append(n)

  #maxCharge[k] is the max number of charge shifts nurse k should work in any given pay period
  maxCharge = {}
  for n in range(chargeNursesLength):
    k = chargeDist[n][0]
    numChargeShifts = chargeDist[n][1]
    numPP = effectivePayPeriods[k]
    numChargePP = math.ceil(numChargeShifts/ numPP)
    maxCharge[k] = numChargePP

  optLength = len(optShifts)

  #availableFridays[k] = [k, numFridaysAvailable, lateFridaysToWork] where numFridaysAvailable is the number of 
  ##Fridays a nurse should be expected to work (6 minus any Fridays she is PTO/ACLS/OFF/Training/PAT/Holiday, and 
  ##adjusted for FTE) and where lateFridaysToWork starts at zero and increments to ultimately become the number of 
  ##late shifts that nurse will be assigned to work on Fridays
  availableFridays = []
  for k in range(numNurses):
    if k in fteNurses:
      #Total the fridays that the nurse is unable to work late shift
      totalPTOFridays = 0
      for p in range(ptoLength):
        nurse = pto[p][0]
        d = pto[p][1]
        if k == nurse and calendar[d].weekday() == 4:
          totalPTOFridays += 1
      totalACLSFridays = 0
      for a in range(aclsShiftsLength):
        nurse = aclsShifts[a][0]
        d = aclsShifts[a][1]
        if k == nurse and calendar[d].weekday() == 4:
          totalACLSFridays += 1
      totalPATFridays = 0
      for p in range(patShiftsLength):
        nurse = patShifts[p][0]
        d = patShifts[p][1]
        if k == nurse and calendar[d].weekday() == 4:
          totalPATFridays += 1
      totalTrainingFridays = 0
      startDateIndex = nurses[k][2]
      c = 0
      while c < startDateIndex:
        d = calendar[c]
        if d.weekday() == 4:
          totalTrainingFridays += 1
        c += 1
      totalOFFFridays = 0
      for f in range(offLength):
        nurse = off[f][0]
        d = off[f][1]
        if k == nurse and calendar[d].weekday() == 4:
          totalOFFFridays += 1
      totalLateOffFridays = 0 #Total Fridays the nurse can work but can't work late shift
      for f in range(shiftOffLength):
        nurse = shiftOff[f][0]
        d = shiftOff[f][1]
        shift = shiftOff[f][2]
        if k == nurse and shift == 2 and calendar[d].weekday() == 4:
          totalLateOffFridays += 1
      #Total the Fridays a nurse is unable to work because the number of PTO/ACLS/etc.
      fte = nurses[k][1]
      numFridaysAvailable = fte * (6 - (totalPTOFridays + totalACLSFridays + totalPATFridays + totalOFFFridays + totalLateOffFridays + totalTrainingFridays + numHolidaysF))

      availableFridays.append([k, numFridaysAvailable, 0])
    else:
      availableFridays.append([k, 0, 0])

  #Sort availableFridays descending based on numFridaysAvailable 
  availableFridays.sort(reverse = True, key = sorting_index_1)

  #Identify the number of late shift Fridays each nurse should work
  totalLateFridaysAssigned = 0
  n = 0
  infiniteLoopDefender = 0
  while totalLateFridaysAssigned < 12:
    if infiniteLoopDefender == numNurses:
      raise Exception('Infinite loop detected #2')
    if availableFridays[n][1] >= 1:
      availableFridays[n][1] -= 1
      availableFridays[n][2] += 1
      totalLateFridaysAssigned += 1
      infiniteLoopDefender = 0
    else:
      infiniteLoopDefender += 1
    if n + 1 < numNurses:
      n += 1
    else:
      n = 0

  #Sort availableFridays ascending based on nurse index
  availableFridays.sort(reverse = False, key = sorting_index_0)

  #totalShiftsPP[pp] = the number of shifts that will be worked in the pay period
  #totalFTEShiftsPP[pp] = the number of shifts that will be worked in the pay period by FTE nurses
  totalShiftsPP = []
  totalFTEShiftsPP = []
  for pp in range(3): #for each pay period
    numOPTPP = 0
    for t in range(optLength):
      d = optShifts[t][1]
      if d < pp * 14 + 14 and d >= pp * 14:
        numOPTPP += 1
    numFTEPP = 0
    for k in fteNurses:
      fte = nurses[k][1]
      numFTEPP += fte * 10
    numPTOPP = 0
    numHolidaysPP = holidaysPP[pp] #the number of holidays in the pay period
    for t in range(ptoLength):
      d = pto[t][1]
      if d < pp * 14 + 14 and d >= pp * 14:
        numPTOPP += 1
    numACLSPP = 0
    for a in range(aclsShiftsLength):
      d = aclsShifts[a][1]
      if d < pp * 14 + 14 and d >= pp * 14:
        numACLSPP += 1
    numTrainingPP = 0
    for k in fteNurses:
      fte = nurses[k][1]
      startDateIndex = nurses[k][2]
      if startDateIndex >= pp * 14 + 14:
        numTrainingPP += fte * 10
      elif startDateIndex > pp * 14 and startDateIndex <= pp * 14 + 7:
        if fte == 1 or fte == 0.8 or fte == 0.6 or fte == 0.4 or fte == 0.2:
          numTrainingPP += fte * 5
        elif fte == 0.9:
          numTrainingPP += 4
        elif fte == 0.7:
          numTrainingPP += 3
        elif fte == 0.5:
          numTrainingPP += 2
        elif fte == 0.3:
          numTrainingPP += 1
    totalShiftsPP.append(numFTEPP + numOPTPP - numPTOPP - numACLSPP - numTrainingPP - numHolidaysPP)
    totalFTEShiftsPP.append(numFTEPP - numPTOPP - numACLSPP - numTrainingPP - numHolidaysPP)

  #dailyTraining[calendarIndex] = the number of FTE nurses unavailable due to being in orientation on that day
  dailyTraining = []
  for i in range(numDays):
    numTraining = 0
    if i not in weekdaysNotHolidays:
      dailyTraining.append(0)
    else:
      for k in fteNurses:
        startDateIndex = nurses[k][2]
        if i < startDateIndex:
          numTraining += 1
      dailyTraining.append(numTraining)

  #dailyOPT[calendarIndex] = the number of OPT shifts on that day
  dailyOPT = []
  for i in range(numDays):
    numOPTShifts = 0
    for t in range(optLength):
      optShiftsCalendarIndex = optShifts[t][1]
      if i == optShiftsCalendarIndex:
        numOPTShifts += 1
    dailyOPT.append(numOPTShifts)

  #demandPP[pp] = the number of shifts (not PTO/ACLS/Training) needed for the pay period
  demandPP = []
  for pp in range(3):
    demandCounter = 0
    for i in range(pp * 14, pp * 14 + 14):
      demandCounter += dailyDemand[i]
    demandPP.append(demandCounter)

  #noBackupLate[pp] = the number of days that don't have a backup late in the pay period
  #dailyBackupLate[calendarIndex] = the number of backup lates that will be assigned to that day
  noBackupLate = []
  dailyBackupLate = []
  for i in range(numDays):
    dailyBackupLate.append(1)
  for pp in range(3):
    numSupplyPP = totalShiftsPP[pp]
    numDemandPP = demandPP[pp]
    noBackupLateCounter = 0
    if numSupplyPP < numDemandPP:
      for i in weekdaysNotHolidays:
        if i >= pp * 14 and i < pp * 14 + 14:
          demand = dailyDemand[i]
          numOPTShifts = dailyOPT[i]
          if numOPTShifts + 4 >= demand:
            noBackupLateCounter += 1
            dailyBackupLate[i] = 0
    noBackupLate.append(noBackupLateCounter)
  
  #patPP[pp] = the number of PAT shifts during the pay period
  patPP = [0, 0, 0]
  for t in range(patShiftsLength):
    calendarIndex = patShifts[t][1]
    pp = 0
    if calendarIndex >= 14 and calendarIndex < 28:
      pp = 1
    elif calendarIndex >= 28:
      pp = 2
    patPP[pp] += 1
  
  #dailyPAT[calendarIndex] = the number of PAT shifts on that day
  dailyPAT = []
  dailyACLS = []
  dailyPTO = []
  dailyOFF = []
  for i in range(numDays):
    dailyPAT.append(0)
    dailyACLS.append(0)
    dailyPTO.append(0)
    dailyOFF.append(0)
  for t in range(patShiftsLength):
    calendarIndex = patShifts[t][1]
    dailyPAT[calendarIndex] += 1
  for a in range(aclsShiftsLength):
    calendarIndex = aclsShifts[a][1]
    dailyACLS[calendarIndex] += 1
  for p in range(ptoLength):
    calendarIndex = pto[p][1]
    dailyPTO[calendarIndex] += 1
  for f in range(offLength):
    calendarIndex = off[f][1]
    dailyOFF[calendarIndex] += 1

  #dailyAvailable[calendarIndex] = the number of FTE nurses that can work an early/middle/late/backup late shift
  dailyAvailable = []
  for i in range(numDays):
    if i not in weekdaysNotHolidays:
      dailyAvailable.append(0)
    else:
      numPAT = dailyPAT[i]
      numPTO = dailyPTO[i]
      numACLS = dailyACLS[i]
      numOFF = dailyOFF[i]
      numTraining = dailyTraining[i]
      numNursesAvailable = fteNursesLength - numOFF - numACLS - numPTO - numPAT - numTraining
      dailyAvailable.append(numNursesAvailable)
    
  #dailyMinNurses[calendarIndex] = the bare minimum number of nurses (FTE + OPT) needed for the day
  dailyMinNurses = []
  for i in range(numDays):
    minNeeded = 0
    if i not in weekdaysNotHolidays:
      dailyMinNurses.append(0)
    else:
      demand = dailyDemand[i]
      if demand == 4:
        minNeeded = 4 #two early and two late
      else:
        minNeeded = 5 #two early, two late, and one backup late
      dailyMinNurses.append(minNeeded)
    
  #middleShiftsFTEPP[pp] = the number of middle shifts worked by FTE nurses in the pay period
  middleShiftsPP = []
  for pp in range(3):
    numSupply = totalFTEShiftsPP[pp] #the number of shifts worked by FTE nurses not in ACLS/PTO/Training
    numEarlyLate = 40 #the total number of early and late shifts
    numNoBackupLate = noBackupLate[pp] #the number of days without a backup late shift
    numBackupLate = 10 - numNoBackupLate #the number of backup late shifts 
    numPAT = patPP[pp] #the number of PAT shifts
    numMiddleShifts = numSupply - numEarlyLate - numPAT - numBackupLate
    middleShiftsPP.append(numMiddleShifts)

  #middleShiftDistPP[pp][calenarIndex] = [calendarIndex, unmetDemand, numMiddleShifts] where unmetDemand is how much demand that day in the pay period that cannot be met by opt, early, late, and backup late, and where numMiddleShifts is the number of middle shifts to assign to that day
  middleShiftDistPP = []
  for pp in range(3):
    middleShiftDistPP.append([])
    numSupplyPP = totalShiftsPP[pp]
    numDemandPP = demandPP[pp]
    for i in range(pp * 14, pp * 14 + 14):
      numOPT = dailyOPT[i] #the number of OPT shifts on this day
      numBackupLate = dailyBackupLate[i] #the number of backup late shifts on this day
      numRegularShifts = 4 #two early, two late
      numPAT = dailyPAT[i] #the number of PAT shifts on this day
      demand = dailyDemand[i] #the number of nurses needed for this day
      unmetDemand = 0
      if i not in weekdaysNotHolidays:
        unmetDemand = -1000
      else:
        unmetDemand = demand - numOPT - numBackupLate - numRegularShifts - numPAT
      middleShiftDistPP[pp].append([i, unmetDemand, 0]) #0 was originally numAssigned

    #sort descending based on unmet demand
    middleShiftDistPP[pp].sort(reverse = True, key = sorting_index_1)

    numMiddleShiftsRemainingPP = middleShiftsPP[pp] #- numMiddleChargePP
    while numMiddleShiftsRemainingPP > 0:
      canAssign = False
      daySelector = 0
      while not canAssign:
        dayToTry = middleShiftDistPP[pp][daySelector]
        calendarIndex = dayToTry[0]
        numAlreadyAssigned = dayToTry[2]
        totalAvail = dailyAvailable[calendarIndex]
        numBackupLate = dailyBackupLate[calendarIndex]
        numEarlyLate = 4
        numNursesAvailable = totalAvail - numEarlyLate - numBackupLate - numAlreadyAssigned
        if numNursesAvailable > 0:
          canAssign = True
          middleShiftDistPP[pp][daySelector][1] -= 1
          middleShiftDistPP[pp][daySelector][2] += 1
          numMiddleShiftsRemainingPP -= 1
          #Sort descending on unmet demand
          middleShiftDistPP[pp].sort(reverse = True, key = sorting_index_1)
        else:
          daySelector += 1
        
  middleShiftDist = []
  for pp in range(3):
    for t in range(len(middleShiftDistPP[pp])):
      middleShiftDist.append(middleShiftDistPP[pp][t])

  middleShiftDist.sort(reverse = False, key = sorting_index_0)

  return [numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
          chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
          aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
          firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
          availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
          dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,scheduleStartDate,
          chargeDist,chargeDistMin,warningMessage,maxEarlyLate,maxBackupLate,maxCharge]

def try_model(numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
              chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
              aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
              firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
              availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
              dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,
              chargeDist,chargeDistMin,maxEarlyLate,maxBackupLate,maxCharge,c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11,c12,c13,
              c14,c15,c16,c17,c18,c19,c20,c21,c22,c23,c24,c25,c26,c27,c28,c29,c30,numSoften):

  #initialize model
  model = LpProblem('FroedtertSargeantCenterPACU',LpMaximize)

  #define decision variables
  daysList = list(range(numDays))
  shiftsList = list(range(numShifts))
  nursesList = list(range(numNurses))
  s = LpVariable.dicts('shift', (daysList,shiftsList,nursesList), lowBound = 0, upBound = 1, cat='Binary')

  #define objective function
  obj = None
  for i in range(numDays):
    for j in range(numShifts):
      for k in range(numNurses):
        if j == 5: #early-charge shift is the third-most desirable type of charge shift
          obj += -10 * s[i][j][k]
        elif j == 6: #middle-charge shift is the most desirable type of charge shift
          obj += 100 * s[i][j][k]
        elif j == 7: #late-charge shift is the least desirable type of charge shift
          obj += -100 * s[i][j][k]
        elif j == 8: #backup-late-charge shift is the second-most desirable type of charge shift
          obj += 10 * s[i][j][k]
        else: #otherwise, there are no costs/benefits
          obj += s[i][j][k]
  
  model += obj

  #constraints
  
  #Constraint 1: A given nurse on a given day can only work 0 or 1 shifts
  if c1:
    for i in range(numDays):
      for k in range(numNurses):
        model += lpSum([s[i][j][k] for j in range(numShifts)]) <= 1
  
  #Constraint 2: There must be exactly one charge nurse shift assigned each weekday
  if c2:
    for i in weekdaysNotHolidays:
      model += lpSum([s[i][j][k] for j in range(5,9) for k in chargeNurses]) == 1

  #Constraint 3: There must be exactly two late nurses each weekday
  if c3:
    for i in weekdaysNotHolidays:
      model += lpSum([s[i][2][k] + s[i][7][k] for k in range(numNurses)]) == 2

  #Constraint 4: There must be exactly two early nurses each weekday
  if c4:
    for i in weekdaysNotHolidays:
      model += lpSum([s[i][0][k] + s[i][5][k] for k in range(numNurses)]) == 2
  
  #Constraint 5: Honor user specification that a given nurse cannot work on a given shift on a given day
  if c5:
    for so in range(shiftOffLength):
      i = shiftOff[so][1]
      j = shiftOff[so][2]
      k = shiftOff[so][0]
      model += s[i][j][k] == 0

  #Constraint 6: Honor approved vacation (PTO + OFF) and ensure that a nurse won't be assigned vacation if they won't be on vacation
  if c6:
    for i in range(numDays):
      for k in range(numNurses):
        isPTO = False
        isOFF = False
        for p in range(ptoLength):
          if i == pto[p][1] and k == pto[p][0]:
            isPTO = True
        if isPTO:
          model += s[i][10][k] == 1
        else:
          model += s[i][10][k] == 0
        for f in range(offLength):
          if i == off[f][1] and k == off[f][0]:
            isOFF = True
        if isOFF:
          model += s[i][11][k] == 1
        else:
          model += s[i][11][k] == 0

  #Constraint 7: Nurses cannot work on weekends or holidays
  if c7:
    for i in range(numDays):
      if i not in weekdaysNotHolidays:
        model += lpSum([s[i][j][k] for j in range(numShifts) for k in range(numNurses)]) == 0
  
  #Constraint 8: OPT nurses must work exactly their requested days  
  if c8:
    optEarly = [] #optEarly[calendarIndex] = the number of OPT nurses assigned an early shift that day
    for c in range(numDays):
      optEarly.append(0)
    for i in range(numDays):
      for k in optNurses:
        iterate = 0
        success = False
        while not success and iterate < optLength:
          nurse = optShifts[iterate][0]
          d = optShifts[iterate][1]
          if k == nurse and i == d:
            success = True
            numNursesAvailable = dailyAvailable[i]
            numMinNeeded = dailyMinNurses[i]
            numOPTShifts = dailyOPT[i]
            numEarlyOPT = optEarly[i]
            if numNursesAvailable >= numMinNeeded:
              model += s[i][1][k] == 1
            else:
              if numMinNeeded - numNursesAvailable == 1 and numEarlyOPT == 0:
                model += s[i][0][k] == 1
                optEarly[i] += 1
              elif numMinNeeded - numNursesAvailable == 2 and numEarlyOPT < 2:
                model += s[i][0][k] == 1
                optEarly[i] += 1
              else:
                model += s[i][1][k] == 1
          else:
            iterate += 1
        if not success:
          for j in range(numShifts):
            model += s[i][j][k] == 0
  """
  #Constraint 9: Early shifts worked should be equitable across nurses
  if c9:
    for k in fteNurses:
      model += lpSum([s[i][0][k] + s[i][5][k] for i in range(numDays)]) >= earlyLate[k] - numSoften
      model += lpSum([s[i][0][k] + s[i][5][k] for i in range(numDays)]) <= earlyLate[k]
  """

  #Constraint 10: Late shifts worked should be equitable across nurses
  if c10:
    for k in fteNurses:
      model += lpSum([s[i][2][k] + s[i][7][k] for i in range(numDays)]) >= earlyLate[k] - numSoften
      model += lpSum([s[i][2][k] + s[i][7][k] for i in range(numDays)]) <= earlyLate[k]
  
  #Constraint 11: Assign the specified PAT shifts, and prevent other shifts from being a PAT shift
  if c11:
    for i in range(numDays):
      for k in fteNurses:
        iterate = 0
        success = False
        while not success and iterate < patShiftsLength:
          d = patShifts[iterate][1]
          nurse = patShifts[iterate][0]
          if k == nurse and i == d:
            success = True
            model += s[i][3][k] == 1
          else:
            iterate += 1
        if not success:
          model += s[i][3][k] == 0
  
  #Constraint 12: 
  #FTE nurses must be assigned their exact FTE hours barring certain situations with holidays, vacation, and orientation
  if c12:
    for pp in range(3):
      numHolidaysPP = holidaysPP[pp] #numHolidaysPP is the number of holidays in the pay period
      for k in range(numNurses):
        numPTO = ptoPP[pp][k] #numPTO is the number of PTO days for nurse k during pay period pp
        numOFF = offPP[pp][k] #numOFF is the number of OFF days for nurse k during pay period pp
        fte = nurses[k][1]
        if k in fteNurses:
          #Enforce this constraint only for nurses not in orientation
          startDateIndex = nurses[k][2]
          constrainPP2 = True
          constrainPP3 = True
          if startDateIndex > 14 and startDateIndex <= 28:
            constrainPP2 = False
          elif startDateIndex > 28:
            constrainPP2 = False
            constrainPP3 = False
          constrainWeek2 = False
          constrainWeek4 = False
          constrainWeek6 = False
          beginIndex = 0
          if startDateIndex > 0 and startDateIndex <= 7:
            constrainWeek2 = True
            beginIndex = 7
          elif startDateIndex > 14 and startDateIndex <= 21:
            constrainWeek4 = True
            beginIndex = 21
          elif startDateIndex > 28 and startDateIndex <= 35:
            constrainWeek6 = True
            beginIndex = 35
          #Set the FTE for the full pay period
          if startDateIndex == 0 or (pp == 1 and constrainPP2) or (pp == 2 and constrainPP3):
            if fte * 10 <= numPTO + numHolidaysPP: #if FTE is less than or equal to the number of vacation days and holidays
              model += lpSum([s[i][j][k] for i in range(pp*14,pp*14+14) for j in range(numShifts)]) == numPTO + numOFF
            else: #otherwise assign the nurse their exact FTE for the pay period
              model += lpSum([s[i][j][k] for i in range(pp*14,pp*14+14) for j in range(numShifts)]) == fte * 10 - numHolidaysPP + numOFF
          #Set the FTE for only the last week in the pay period
          elif (pp == 0 and constrainWeek2) or (pp == 1 and constrainWeek4) or (pp == 2 and constrainWeek6):
            numShouldWork = 0
            if fte == 1 or fte == 0.8 or fte == 0.6 or fte == 0.4 or fte == 0.2:
              numShouldWork = fte * 5
            elif fte == 0.9:
              numShouldWork = 5
            elif fte == 0.7:
              numShouldWork = 4
            elif fte == 0.5:
              numShouldWork = 3
            elif fte == 0.3:
              numShouldWork = 2
            elif fte == 0.1:
              numShouldWork = 1
            if numShouldWork <= numPTO + numHolidaysPP: #if FTE is less than or equal to the number of vacation days and holidays
              model += lpSum([s[i][j][k] for i in range(beginIndex,beginIndex + 7) for j in range(numShifts)]) == numPTO + numOFF
            else: #otherwise assign the nurse their exact FTE for the week
              model += lpSum([s[i][j][k] for i in range(beginIndex,beginIndex + 7) for j in range(numShifts)]) == numShouldWork - numHolidaysPP + numOFF
  
  #Constraint 13:
  #Constraint 13A: Each nurse should have balanced workweeks. For example, a 0.8 nurse should work 4 days every M-F. A 0.7 nurse should work 3 or 4 days each M-F.
  ##Since we already have constraint 12 which assigns exact FTE hours for a pay period, we only need to make sure a nurse isn't working over their FTE on a given M-F
  ##Constraint 13B: Odd-numbered FTE nurses should ideally work an alternating number of days each workweek (e.g. 0.7 nurse should not work two consecutive 4-day workweeks; should be 3-4-3-4-3-4 or 4-3-4-3-4-3 ideally), so this constraint prevents a 0.7 nurse for example from working two consecutive 4-day workweeks, similar for 0.1, 0.3, 0.5, 0.9
  if c13:
    for ww in range(6):
      pp = 0
      if ww == 2 or ww == 3:
        pp = 1
      elif ww == 4 or ww == 5:
        pp = 2
      for k in fteNurses:
        fte = nurses[k][1]
        #Identify the min number of days a nurse should work in a given Monday-Friday workweek
        minShouldWork = 0
        isInTraining = False
        numToSubtractFromMin = 0
        startDateIndex = nurses[k][2]
        #If in training, then min is zero.
        if ww <= 1 and startDateIndex > 0:
          isInTraining = True
        elif ww <= 3 and startDateIndex > 14:
          isInTraining = True
        elif ww <= 5 and startDateIndex > 28:
          isInTraining = True
        else: #add up PTO and holidays. Divide the total by 2. Take the floor. That's how much you subtract from min
          numPTOPP = ptoPP[pp][k]
          numHolidaysPP = holidaysPP[pp]
          totalPTOAndHolidaysObserved = numPTOPP + numHolidaysPP
          numToSubtractFromMin = math.floor(totalPTOAndHolidaysObserved / 2.0)
        #Identify the max number of days a nurse should work in a given Monday-Friday workweek
        maxShouldWork = 0
        if fte >= 0.9:
          maxShouldWork = 5
          minShouldWork = 0
        elif fte >= 0.7:
          maxShouldWork = 4
          if isInTraining:
            minShouldWork = 0
          else:
            minShouldWork = max(3 - numToSubtractFromMin, 0)
        elif fte >= 0.5:
          maxShouldWork = 3
          if isInTraining:
            minShouldWork = 0
          else:
            minShouldWork = max(2 - numToSubtractFromMin, 0)
        elif fte >= 0.3:
          maxShouldWork = 2
          if isInTraining:
            minShouldWork = 0
          else:
            minShouldWork = max(1 - numToSubtractFromMin, 0)
        elif fte >= 0.1:
          maxShouldWork = 1
          minShouldWork = 0
        lowerBound = max(minShouldWork - numSoften, 0)
        numDaysInWeek = 5
        if ww == 5: #if it's the last workweek which is a Mon-Thu
          numDaysInWeek = 4
        #Constraint for balanced workweeks
        model += lowerBound <= lpSum([s[i][j][k] for i in range(ww*7 + firstMonday, ww*7 + firstMonday + numDaysInWeek) for j in range(numShifts - 2)]) <= maxShouldWork
        #Constraint to prevent 0.7 from having two consecutive workweeks of 4 days, 0.5 from 3 days, 0.3 from 2 days
        if ww < 4 and fte in (0.1,0.3,0.5,0.7,0.9): #only set the constraint for the first 5 weeks since evaluating for the last workweek would be out of range
          model += lpSum([s[i][j][k] + s[i + 7][j][k] for i in range(ww*7 + firstMonday, ww*7 + firstMonday + numDaysInWeek) for j in range(numShifts - 2)]) <= maxShouldWork * 2 - 1
  
  #Constraint 14: A nurse cannot work late shift one day and then early shift the very next day
  if c14:
    for i in range(numDays - 1):
      for k in range(numNurses):
        model += s[i][2][k] + s[i + 1][0][k] <= 1
        model += s[i][2][k] + s[i + 1][5][k] <= 1
        model += s[i][7][k] + s[i + 1][0][k] <= 1
        model += s[i][7][k] + s[i + 1][5][k] <= 1
  
  #Constraint 15: Spread out late/backup late shifts evenly across pay periods, adjusting for number of days unavailable to work early/late/backup late.
  if c15:
    for k in fteNurses:
      startDateIndex = nurses[k][2]
      constraintApplies = True
      startIndexPP = 0
      if startDateIndex > 0 and startDateIndex <= 14: #apply the constraint only to the last two pay periods
        startIndexPP = 1
      elif startDateIndex > 14:
        constraintApplies = False
      if constraintApplies:
        numEarlyLatePP = maxEarlyLate[k]
        numBackupLatePP = maxBackupLate[k]
        for pp in range(startIndexPP, 3):
          #model += lpSum([s[i][0][k] + s[i][5][k] for i in range(pp*14,pp*14+14)]) <= numEarlyLatePP
          model += lpSum([s[i][2][k] + s[i][7][k] for i in range(pp*14,pp*14+14)]) <= numEarlyLatePP
          model += lpSum([s[i][4][k] + s[i][8][k] for i in range(pp*14,pp*14+14)]) <= numBackupLatePP
  
  #Constraint 16: Assign zero or one backup late shifts every day
  if c16:
    for i in weekdaysNotHolidays:
      pp = 0
      if i >= 14 and i < 28:
        pp = 1
      elif i >= 28 and i < 42:
        pp = 2
      numSupplyPP = totalShiftsPP[pp]
      numDemandPP = demandPP[pp]
      demand = dailyDemand[i]
      numOPTShifts = dailyOPT[i]
      constraint = None
      if numOPTShifts + 4 >= demand and numSupplyPP < numDemandPP:
        constraint = 0
      else:
        constraint = 1
      model += lpSum([s[i][4][k] + s[i][8][k] for k in range(numNurses)]) == constraint

  #Constraint 17: The number of Mondays and Fridays worked should be equitable
  if c17:
    for k in fteNurses:
      fte = nurses[k][1]
      maxMF = DataHandling.get_max_mf_worked(fte)
      model += lpSum([s[i][j][k] for i in allMondaysAndFridays for j in range(numShifts - 2)]) <= maxMF

  #Constraint 18: The number of charge shifts assigned should be equitable across charge nurses
  if c18:
    for n in range(chargeNursesLength):
      k = chargeDist[n][0]
      numChargeShifts = chargeDist[n][1]
      numChargeShiftsMin = chargeDistMin[n][1]
      model += numChargeShiftsMin <= lpSum([s[i][j][k] for i in range(numDays) for j in range(5,9)]) <= numChargeShifts

  #Constraint 19: The number of backup late shifts worked should be equitable across nurses
  if c19:
    for k in range(numNurses):
      model += lpSum([s[i][4][k] + s[i][8][k] for i in range(numDays)]) >= backupLate[k] - numSoften
      model += lpSum([s[i][4][k] + s[i][8][k] for i in range(numDays)]) <= backupLate[k]
  
  #Constraint 20: Non-charge nurses cannot be assigned charge shifts
  if c20:
    model += lpSum([s[i][j][k] for i in range(numDays) for j in range(5,9) for k in nonChargeNurses]) == 0

  #Constraint 21: A nurse cannot work two consecutive late shifts
  if c21:
    for i in range(numDays - 1):
      for k in range(numNurses):
        model += s[i][2][k] + s[i + 1][2][k] <= 1
        model += s[i][2][k] + s[i + 1][7][k] <= 1
        model += s[i][7][k] + s[i + 1][2][k] <= 1
        model += s[i][7][k] + s[i + 1][7][k] <= 1
  
  #Constraint 22: Assign ACLS shifts, and prevent assigning ACLS shifts to people not doing it
  if c22:
    for i in range(numDays):
      for k in range(numNurses):
        iterate = 0
        success = False
        while not success and iterate < aclsShiftsLength:
          nurse = aclsShifts[iterate][0]
          d = aclsShifts[iterate][1]
          if k == nurse and i == d:
            success = True
            model += s[i][9][k] == 1
          else:
            iterate += 1
        if not success:
          model += s[i][9][k] == 0
  
  #Constraint 23: Ensure that nurses in orientation are not assigned a shift
  if c23:
    for k in fteNurses:
      startDateIndex = nurses[k][2]
      if startDateIndex > 0:
        model += lpSum([s[i][j][k] for i in range(startDateIndex) for j in range(numShifts)]) == 0
  
  #Constraint 24: Late shifts worked on Fridays should be equitable across nurses
  if c24:
    for k in fteNurses:
      model += lpSum([s[i][2][k] + s[i][7][k] for i in allFridays]) <= availableFridays[k][2]
  
  #Constraint 25: Spread out charge shifts evenly across pay periods, adjusting for number of days unavailable to work early/late/backup late.
  if c25:
    for n in range(chargeNursesLength):
      k = chargeDist[n][0]
      startDateIndex = nurses[k][2]
      constraintApplies = True
      startIndexPP = 0
      if startDateIndex > 0 and startDateIndex <= 14: #apply the constraint only to the last two pay periods
        startIndexPP = 1
      elif startDateIndex > 14:
        constraintApplies = False
      if constraintApplies:
        numChargePP = maxCharge[k]
        for pp in range(startIndexPP, 3):
          model += lpSum([s[i][j][k] for i in range(pp*14,pp*14+14) for j in range(5,9)]) <= numChargePP
  
  #Constraint 27: Assign an exact number of middle shifts to the most in-demand days, or apply a softer approach with a range of middle shifts to apply
  if c27:
    for i in weekdaysNotHolidays:
      pp = 0
      if i >= 14 and i < 28:
        pp = 1
      elif i >= 28 and i < 42:
        pp = 2
      supply = totalShiftsPP[pp]
      demand = demandPP[pp]
      untappedDemand = middleShiftDist[i][1]
      if untappedDemand < 0:
        untappedDemand = 0
      numMiddleShifts = middleShiftDist[i][2]
      if supply >= demand:
        lowerBound = max(numMiddleShifts - numSoften, 0)
        model += lowerBound <= lpSum([s[i][1][k] + s[i][6][k] for k in fteNurses]) <= numMiddleShifts + numSoften
      else:
        if numMiddleShifts > 0:
          upperBound = numMiddleShifts + numSoften
          lowerBound = max(numMiddleShifts - numSoften, 0)
          model += lowerBound <= lpSum([s[i][1][k] + s[i][6][k] for k in fteNurses]) <= upperBound
        else:
          model += lpSum([s[i][1][k] + s[i][6][k] for k in fteNurses]) <= untappedDemand

  #Constraint 28: A nurse cannot work two consecutive charge shifts
  if c28:
    for i in range(numDays - 1):
      for k in range(numNurses):
        for j1 in range(5,9):
          for j2 in range(5,9):
            model += s[i][j1][k] + s[i + 1][j2][k] <= 1
  
  #solve the model
  model.solve()
  
  return [model, LpStatus[model.status]]  


def get_result(processedUserInput):
  numNurses = processedUserInput[0]
  numDays = processedUserInput[1]
  numShifts = processedUserInput[2]
  nurses = processedUserInput[3]
  calendar = processedUserInput[4]
  holidays = processedUserInput[5]
  pto = processedUserInput[6]
  off = processedUserInput[7]
  shiftOff = processedUserInput[8]
  shiftOffLength = processedUserInput[9]
  weekdaysNotHolidays = processedUserInput[10]
  chargeNurses = processedUserInput[11]
  patShifts = processedUserInput[12]
  patShiftsLength = processedUserInput[13]
  fteNurses = processedUserInput[14]
  optNurses = processedUserInput[15]
  optShifts = processedUserInput[16]
  aclsShifts = processedUserInput[17]
  allFridays = processedUserInput[18]
  allMondays = processedUserInput[19]
  allMondaysAndFridays = processedUserInput[20]
  numHolidaysMF = processedUserInput[21]
  holidaysPP = processedUserInput[22]
  ptoPP = processedUserInput[23]
  offPP = processedUserInput[24]
  firstMonday = processedUserInput[25]
  earlyLate = processedUserInput[26]
  backupLate = processedUserInput[27]
  chargeNursesLength = processedUserInput[28]
  nonChargeNurses = processedUserInput[29]
  availableFridays = processedUserInput[30]
  effectivePayPeriods = processedUserInput[31]
  totalShiftsPP = processedUserInput[32]
  totalFTEShiftsPP = processedUserInput[33]
  dailyOPT = processedUserInput[34]
  demandPP = processedUserInput[35]
  dailyDemand = processedUserInput[36]
  middleShiftDist = processedUserInput[37]
  dailyAvailable = processedUserInput[38]
  dailyMinNurses = processedUserInput[39]
  ptoLength = processedUserInput[40]
  offLength = processedUserInput[41]
  optLength = processedUserInput[42]
  aclsShiftsLength = processedUserInput[43]
  scheduleStartDate = processedUserInput[44]
  chargeDist = processedUserInput[45]
  chargeDistMin = processedUserInput[46]
  warningMessage = processedUserInput[47]
  maxEarlyLate = processedUserInput[48]
  maxBackupLate = processedUserInput[49]
  maxCharge = processedUserInput[50]
  
  opt = None
  solution = None
  status = None

  opt = try_model(numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
                  chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
                  aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
                  firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
                  availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
                  dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,
                  chargeDist,chargeDistMin,maxEarlyLate,maxBackupLate,maxCharge,c1=True,c2=True,
                  c3=True,c4=True,c5=True,c6=True,c7=True,c8=True,c9=True,c10=True,c11=True,c12=True,c13=True,
                  c14=True,c15=True,c16=True,c17=True,c18=True,c19=True,c20=True,c21=True,c22=True,c23=True,
                  c24=True,c25=True,c26=True,c27=True,c28=True,c29=True,c30=True,numSoften=0)
  solution = opt[0]
  status = opt[1]
  if status == 'Optimal':
    print(status)
    return [solution, status]

  opt = try_model(numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
                  chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
                  aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
                  firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
                  availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
                  dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,
                  chargeDist,chargeDistMin,maxEarlyLate,maxBackupLate,maxCharge,c1=True,c2=True,
                  c3=True,c4=True,c5=True,c6=True,c7=True,c8=True,c9=True,c10=True,c11=True,c12=True,c13=True,
                  c14=True,c15=True,c16=True,c17=True,c18=True,c19=True,c20=True,c21=True,c22=True,c23=True,
                  c24=True,c25=True,c26=True,c27=True,c28=True,c29=True,c30=True,numSoften=1)
  solution = opt[0]
  status = opt[1]
  if status == 'Optimal':
    print(status)
    return [solution, status]

  opt = try_model(numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
                  chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
                  aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
                  firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
                  availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
                  dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,
                  chargeDist,chargeDistMin,maxEarlyLate,maxBackupLate,maxCharge,c1=True,c2=True,
                  c3=True,c4=True,c5=True,c6=True,c7=True,c8=True,c9=True,c10=True,c11=True,c12=True,c13=True,
                  c14=True,c15=True,c16=True,c17=True,c18=True,c19=True,c20=True,c21=True,c22=True,c23=True,
                  c24=True,c25=True,c26=True,c27=True,c28=True,c29=True,c30=True,numSoften=2)
  solution = opt[0]
  status = opt[1]
  if status == 'Optimal':
    print(status)
    return [solution, status]

  opt = try_model(numNurses,numDays,numShifts,nurses,calendar,holidays,pto,off,shiftOff,shiftOffLength,weekdaysNotHolidays,
                  chargeNurses,patShifts,patShiftsLength,fteNurses,optNurses,optShifts,
                  aclsShifts,allFridays,allMondays,allMondaysAndFridays,numHolidaysMF,holidaysPP,ptoPP,offPP,
                  firstMonday,earlyLate,backupLate,chargeNursesLength,nonChargeNurses,
                  availableFridays,effectivePayPeriods,totalShiftsPP,totalFTEShiftsPP,dailyOPT,demandPP,
                  dailyDemand,middleShiftDist,dailyAvailable,dailyMinNurses,ptoLength,offLength,optLength,aclsShiftsLength,
                  chargeDist,chargeDistMin,maxEarlyLate,maxBackupLate,maxCharge,c1=True,c2=True,
                  c3=True,c4=True,c5=True,c6=True,c7=True,c8=True,c9=True,c10=True,c11=True,c12=True,c13=True,
                  c14=True,c15=True,c16=True,c17=True,c18=True,c19=True,c20=True,c21=True,c22=True,c23=True,
                  c24=True,c25=True,c26=True,c27=True,c28=True,c29=True,c30=True,numSoften=3)
  solution = opt[0]
  status = opt[1]
  if status == 'Optimal':
    print(status)
    return [solution, status]

  print(status)
  return [solution, status] #Return status to indicate the problem is infeasible

def export_schedule(result,processedUserInput,scheduleID,instanceID,instanceName):
  solution = result[0]
  status = result[1]

  numNurses = processedUserInput[0]
  numDays = processedUserInput[1]
  numShifts = processedUserInput[2]
  nurses = processedUserInput[3]
  calendar = processedUserInput[4]
  holidays = processedUserInput[5]
  weekdaysNotHolidays = processedUserInput[10]
  fteNurses = processedUserInput[14]
  dailyDemand = processedUserInput[36]
  scheduleStartDate = processedUserInput[44]

  DataHandling.add_instance(scheduleID,instanceID,instanceName)
  
  #get variables whose value is 1
  V1 = set() #The set of all variables equal to 1
  for v in solution.variables():
    if v.varValue == 1:
      V1.add(v.name)
  
  #organize the set into a list
  #schedule[day][nurse] is a list that returns the shift that a given nurse works on a given day
  schedule = []
  for i in range(numDays):
    schedule.append([])
    for k in range(numNurses):
      schedule[i].append(-1)
      for v in V1:
        if v == 'shift_' + str(i) + '_0_' + str(k):
          schedule[i][k] = 0
        elif v == 'shift_' + str(i) + '_1_' + str(k):
          schedule[i][k] = 1
        elif v == 'shift_' + str(i) + '_2_' + str(k):
          schedule[i][k] = 2
        elif v == 'shift_' + str(i) + '_3_' + str(k):
          schedule[i][k] = 3
        elif v == 'shift_' + str(i) + '_4_' + str(k):
          schedule[i][k] = 4
        elif v == 'shift_' + str(i) + '_5_' + str(k):
          schedule[i][k] = 5
        elif v == 'shift_' + str(i) + '_6_' + str(k):
          schedule[i][k] = 6
        elif v == 'shift_' + str(i) + '_7_' + str(k):
          schedule[i][k] = 7
        elif v == 'shift_' + str(i) + '_8_' + str(k):
          schedule[i][k] = 8
        elif v == 'shift_' + str(i) + '_9_' + str(k):
          schedule[i][k] = 9
        elif v == 'shift_' + str(i) + '_10_' + str(k):
          schedule[i][k] = 10
        elif v == 'shift_' + str(i) + '_11_' + str(k):
          schedule[i][k] = 11

  #Store data into header and data lists
  header1 = ["NURSE", "FTE"]
  for pp in range(3):
    for i in range(pp*14,pp*14+14):
      d = calendar[i]
      if d.weekday() >= 0 and d.weekday() <= 4: #if it's a weekday
        header1.append(datetime.strptime(str(d),'%Y-%m-%d').strftime('%m/%d'))
    header1.append("DATE")

  app_tables.generatedschedules.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    row_type = 'header1',
    nurse_names = header1[0],
    fte = header1[1],
    day_1 = header1[2],
    day_2 = header1[3],
    day_3 = header1[4],
    day_4 = header1[5],
    day_5 = header1[6],
    day_6 = header1[7],
    day_7 = header1[8],
    day_8 = header1[9],
    day_9 = header1[10],
    day_10 = header1[11],
    nurse_names_2 = header1[12],
    day_11 = header1[13],
    day_12 = header1[14],
    day_13 = header1[15],
    day_14 = header1[16],
    day_15 = header1[17],
    day_16 = header1[18],
    day_17 = header1[19],
    day_18 = header1[20],
    day_19 = header1[21],
    day_20 = header1[22],
    nurse_names_3 = header1[23],
    day_21 = header1[24],
    day_22 = header1[25],
    day_23 = header1[26],
    day_24 = header1[27],
    day_25 = header1[28],
    day_26 = header1[29],
    day_27 = header1[30],
    day_28 = header1[31],
    day_29 = header1[32],
    day_30 = header1[33],
    nurse_names_4 = header1[34]
  )

  header2 = ["", ""]
  for pp in range(3):
    for i in range(pp*14,pp*14+14):
      dayOfWeek = calendar[i].weekday()
      if dayOfWeek == 0:
        header2.append('MON')
      elif dayOfWeek == 1:
        header2.append('TUE')
      elif dayOfWeek == 2:
        header2.append('WED')
      elif dayOfWeek == 3:
        header2.append('THU')
      elif dayOfWeek == 4:
        header2.append('FRI')
    header2.append("DAY")

  app_tables.generatedschedules.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    row_type = 'header2',
    nurse_names = header2[0],
    fte = header2[1],
    day_1 = header2[2],
    day_2 = header2[3],
    day_3 = header2[4],
    day_4 = header2[5],
    day_5 = header2[6],
    day_6 = header2[7],
    day_7 = header2[8],
    day_8 = header2[9],
    day_9 = header2[10],
    day_10 = header2[11],
    nurse_names_2 = header2[12],
    day_11 = header2[13],
    day_12 = header2[14],
    day_13 = header2[15],
    day_14 = header2[16],
    day_15 = header2[17],
    day_16 = header2[18],
    day_17 = header2[19],
    day_18 = header2[20],
    day_19 = header2[21],
    day_20 = header2[22],
    nurse_names_3 = header2[23],
    day_21 = header2[24],
    day_22 = header2[25],
    day_23 = header2[26],
    day_24 = header2[27],
    day_25 = header2[28],
    day_26 = header2[29],
    day_27 = header2[30],
    day_28 = header2[31],
    day_29 = header2[32],
    day_30 = header2[33],
    nurse_names_4 = header2[34]
  )
  
  for k in range(numNurses):
    name = nurses[k][0]
    r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
    userID = r['user_id']
    fte = nurses[k][1]
    startDateIndex = nurses[k][2]
    nurseData = []
    nurseData.append(name)
    if startDateIndex > 0:
      nurseData.append("ORIENT")
    elif k in fteNurses:
      nurseData.append(fte)
    else:
      nurseData.append("OPT")
    for pp in range(3):
      for i in range(pp*14,pp*14+14):
        d = calendar[i]
        dayOfWeek = d.weekday()
        if dayOfWeek >= 0 and dayOfWeek <= 4: #if it's a weekday...
          shift = schedule[i][k]
          if shift == -1:
            if i in holidays:
              nurseData.append("H")
            else:
              nurseData.append("")
          elif shift == 0:
            nurseData.append("6")
          elif shift == 1:
            nurseData.append("7")
          elif shift == 2:
            nurseData.append("8")
          elif shift == 3:
            nurseData.append("PAT")
          elif shift == 4:
            nurseData.append("7*")
          elif shift == 5:
            nurseData.append("6-C")
          elif shift == 6:
            nurseData.append("7-C")
          elif shift == 7:
            nurseData.append("8-C")
          elif shift == 8:
            nurseData.append("7*-C")
          elif shift == 9:
            nurseData.append("ACLS")
          elif shift == 10:
            nurseData.append("PTO")
          elif shift == 11:
            nurseData.append("Off")
      nurseData.append(name)
    app_tables.generatedschedules.add_row(
      schedule_id = scheduleID,
      instance_id = instanceID,
      row_type = 'data',
      user_id = userID,
      nurse_names = nurseData[0],
      fte = str(nurseData[1]),
      fte_sortable = DataHandling.get_fte_sortable(userID,fte),
      day_1 = nurseData[2],
      day_2 = nurseData[3],
      day_3 = nurseData[4],
      day_4 = nurseData[5],
      day_5 = nurseData[6],
      day_6 = nurseData[7],
      day_7 = nurseData[8],
      day_8 = nurseData[9],
      day_9 = nurseData[10],
      day_10 = nurseData[11],
      nurse_names_2 = nurseData[12],
      day_11 = nurseData[13],
      day_12 = nurseData[14],
      day_13 = nurseData[15],
      day_14 = nurseData[16],
      day_15 = nurseData[17],
      day_16 = nurseData[18],
      day_17 = nurseData[19],
      day_18 = nurseData[20],
      day_19 = nurseData[21],
      day_20 = nurseData[22],
      nurse_names_3 = nurseData[23],
      day_21 = nurseData[24],
      day_22 = nurseData[25],
      day_23 = nurseData[26],
      day_24 = nurseData[27],
      day_25 = nurseData[28],
      day_26 = nurseData[29],
      day_27 = nurseData[30],
      day_28 = nurseData[31],
      day_29 = nurseData[32],
      day_30 = nurseData[33],
      nurse_names_4 = nurseData[34]
    )

  footer1 = ['-','-','-','-','-','-','-','-','-','-','-','-','TOTAL (PP1)','-','-','-','-','-','-','-','-','-','-','TOTAL (PP2)','-','-','-','-','-','-','-','-','-','-','TOTAL (PP3)']
  app_tables.generatedschedules.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    row_type = 'footer1',
    nurse_names = '-',
    fte = '-',
    day_1 = '-',
    day_2 = '-',
    day_3 = '-',
    day_4 = '-',
    day_5 = '-',
    day_6 = '-',
    day_7 = '-',
    day_8 = '-',
    day_9 = '-',
    day_10 = '-',
    nurse_names_2 = 'TOTAL (PP1)',
    day_11 = '-',
    day_12 = '-',
    day_13 = '-',
    day_14 = '-',
    day_15 = '-',
    day_16 = '-',
    day_17 = '-',
    day_18 = '-',
    day_19 = '-',
    day_20 = '-',
    nurse_names_3 = 'TOTAL (PP2)',
    day_21 = '-',
    day_22 = '-',
    day_23 = '-',
    day_24 = '-',
    day_25 = '-',
    day_26 = '-',
    day_27 = '-',
    day_28 = '-',
    day_29 = '-',
    day_30 = '-',
    nurse_names_4 = 'TOTAL (PP3)'
  )

  footerSupply = ['# RNs Working','']
  footerDemand = ['# RNs Needed','']
  for pp in range(3):
    numSupplyPP = 0
    numDemandPP = 0
    for i in range(pp*14,pp*14+14):
      if i in weekdaysNotHolidays:
        numSupply = 0
        numDemand = dailyDemand[i]
        for k in range(numNurses):
          shift = schedule[i][k]
          if shift in (0,1,2,4,5,6,7,8):
            numSupply += 1
            numSupplyPP += 1
        numDemandPP += numDemand
        footerSupply.append(str(numSupply))
        footerDemand.append(str(numDemand))
      elif i in holidays:
        footerSupply.append('0')
        footerDemand.append('0')
    footerSupply.append(str(numSupplyPP))
    footerDemand.append(str(numDemandPP))

  app_tables.generatedschedules.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    row_type = 'footer2',
    nurse_names = footerSupply[0],
    fte = footerSupply[1],
    day_1 = footerSupply[2],
    day_2 = footerSupply[3],
    day_3 = footerSupply[4],
    day_4 = footerSupply[5],
    day_5 = footerSupply[6],
    day_6 = footerSupply[7],
    day_7 = footerSupply[8],
    day_8 = footerSupply[9],
    day_9 = footerSupply[10],
    day_10 = footerSupply[11],
    nurse_names_2 = footerSupply[12],
    day_11 = footerSupply[13],
    day_12 = footerSupply[14],
    day_13 = footerSupply[15],
    day_14 = footerSupply[16],
    day_15 = footerSupply[17],
    day_16 = footerSupply[18],
    day_17 = footerSupply[19],
    day_18 = footerSupply[20],
    day_19 = footerSupply[21],
    day_20 = footerSupply[22],
    nurse_names_3 = footerSupply[23],
    day_21 = footerSupply[24],
    day_22 = footerSupply[25],
    day_23 = footerSupply[26],
    day_24 = footerSupply[27],
    day_25 = footerSupply[28],
    day_26 = footerSupply[29],
    day_27 = footerSupply[30],
    day_28 = footerSupply[31],
    day_29 = footerSupply[32],
    day_30 = footerSupply[33],
    nurse_names_4 = footerSupply[34]
  )

  app_tables.generatedschedules.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    row_type = 'footer3',
    nurse_names = footerDemand[0],
    fte = footerDemand[1],
    day_1 = footerDemand[2],
    day_2 = footerDemand[3],
    day_3 = footerDemand[4],
    day_4 = footerDemand[5],
    day_5 = footerDemand[6],
    day_6 = footerDemand[7],
    day_7 = footerDemand[8],
    day_8 = footerDemand[9],
    day_9 = footerDemand[10],
    day_10 = footerDemand[11],
    nurse_names_2 = footerDemand[12],
    day_11 = footerDemand[13],
    day_12 = footerDemand[14],
    day_13 = footerDemand[15],
    day_14 = footerDemand[16],
    day_15 = footerDemand[17],
    day_16 = footerDemand[18],
    day_17 = footerDemand[19],
    day_18 = footerDemand[20],
    day_19 = footerDemand[21],
    day_20 = footerDemand[22],
    nurse_names_3 = footerDemand[23],
    day_21 = footerDemand[24],
    day_22 = footerDemand[25],
    day_23 = footerDemand[26],
    day_24 = footerDemand[27],
    day_25 = footerDemand[28],
    day_26 = footerDemand[29],
    day_27 = footerDemand[30],
    day_28 = footerDemand[31],
    day_29 = footerDemand[32],
    day_30 = footerDemand[33],
    nurse_names_4 = footerDemand[34]
  )

  for row in app_tables.cna.search(schedule_id = scheduleID,included_in_roster_tf = True): #for each row
    nurseName = row['nurse_name']
    d1 = row['day_1']
    d2 = row['day_2']
    d3 = row['day_3']
    d4 = row['day_4']
    d5 = row['day_5']
    d6 = row['day_6']
    d7 = row['day_7']
    d8 = row['day_8']
    d9 = row['day_9']
    d10 = row['day_10']
    d11 = row['day_11']
    d12 = row['day_12']
    d13 = row['day_13']
    d14 = row['day_14']
    d15 = row['day_15']
    d16 = row['day_16']
    d17 = row['day_17']
    d18 = row['day_18']
    d19 = row['day_19']
    d20 = row['day_20']
    d21 = row['day_21']
    d22 = row['day_22']
    d23 = row['day_23']
    d24 = row['day_24']
    d25 = row['day_25']
    d26 = row['day_26']
    d27 = row['day_27']
    d28 = row['day_28']
    d29 = row['day_29']
    d30 = row['day_30']
    footerCNA = [nurseName,'',d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,nurseName,d11,d12,d13,d14,d15,d16,d17,d18,d19,d20,nurseName,d21,d22,d23,d24,d25,d26,d27,d28,d29,d30,nurseName]
    app_tables.generatedschedules.add_row(
      schedule_id = scheduleID,
      instance_id = instanceID,
      row_type = 'footer5',
      nurse_names = footerCNA[0],
      fte = footerCNA[1],
      day_1 = footerCNA[2],
      day_2 = footerCNA[3],
      day_3 = footerCNA[4],
      day_4 = footerCNA[5],
      day_5 = footerCNA[6],
      day_6 = footerCNA[7],
      day_7 = footerCNA[8],
      day_8 = footerCNA[9],
      day_9 = footerCNA[10],
      day_10 = footerCNA[11],
      nurse_names_2 = footerCNA[12],
      day_11 = footerCNA[13],
      day_12 = footerCNA[14],
      day_13 = footerCNA[15],
      day_14 = footerCNA[16],
      day_15 = footerCNA[17],
      day_16 = footerCNA[18],
      day_17 = footerCNA[19],
      day_18 = footerCNA[20],
      day_19 = footerCNA[21],
      day_20 = footerCNA[22],
      nurse_names_3 = footerCNA[23],
      day_21 = footerCNA[24],
      day_22 = footerCNA[25],
      day_23 = footerCNA[26],
      day_24 = footerCNA[27],
      day_25 = footerCNA[28],
      day_26 = footerCNA[29],
      day_27 = footerCNA[30],
      day_28 = footerCNA[31],
      day_29 = footerCNA[32],
      day_30 = footerCNA[33],
      nurse_names_4 = footerCNA[34]
    )

#Try optimizing using all constraints. If that doesn't work, try loosening the solution space by neglecting certain constraints
@anvil.server.background_task
def get_optimal_solution_background(scheduleID,instanceName):
  instanceID = DataHandling.get_new_instance_id(scheduleID)
  errorMessage = check_for_feasibility_issues(scheduleID)
  warningMessage = ''
  if errorMessage == '':
    userInput = get_user_input(scheduleID)
    processedUserInput = process_user_input(userInput)
    warningMessage = processedUserInput[47]
    result = get_result(processedUserInput)
    status = result[1]
    if status != 'Optimal':
      anvil.server.task_state['status'] = status
      anvil.server.task_state['error_message'] = ''
      anvil.server.task_state['warning_message'] = warningMessage
      anvil.server.task_state['instance_id'] = instanceID
      return
    export_schedule(result,processedUserInput,scheduleID,instanceID,instanceName)
    numDays = userInput[1]
    nurses = userInput[2]
    calendar = userInput[4]
    holidays = userInput[5]
    chargeNurses = processedUserInput[11]
    earlyLate = processedUserInput[26]
    backupLate = processedUserInput[27]
    availableFridays = processedUserInput[30]
    chargeDist = processedUserInput[45]
    maxEarlyLate = processedUserInput[48]
    maxBackupLate = processedUserInput[49]
    maxCharge = processedUserInput[50]
    DataHandling.initialize_instance_stats(scheduleID,instanceID,nurses,earlyLate,backupLate,maxEarlyLate,maxBackupLate,availableFridays,maxCharge,chargeNurses,chargeDist,holidays,numDays,calendar)
    anvil.server.task_state['status'] = status
    anvil.server.task_state['error_message'] = ''
    anvil.server.task_state['warning_message'] = ''
    anvil.server.task_state['instance_id'] = instanceID
    return
  anvil.server.task_state['status'] = 'Infeasible'
  anvil.server.task_state['error_message'] = errorMessage
  anvil.server.task_state['warning_message'] = ''
  anvil.server.task_state['instance_id'] = instanceID
  return

@anvil.server.callable
def get_optimal_solution(scheduleID, instanceName):
  task = anvil.server.launch_background_task('get_optimal_solution_background',scheduleID,instanceName)
  return task
