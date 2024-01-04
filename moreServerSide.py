import anvil.email
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server
from datetime import *
from io import StringIO
import csv
import holidays
import anvil.tz
import math

#####MISCELLANEOUS#####

#accept a date parameter and return that date's calendar index
def get_calendar_index(d, calendar, numDays):
  gotIndex = False
  c = 0
  while not gotIndex and c < numDays:
    calDate = calendar[c]
    if (calDate == d):
      return c
    c += 1

#accept a nurse name and return the nurse index
def get_nurse_index(n, nurses, numNurses):
  gotIndex = False
  i = 0
  while not gotIndex and i < numNurses:
    nurseName = nurses[i][0]
    if (nurseName == n):
      return i
    i += 1

#check if there are duplicates in a given list. If so, return the first item found that is a duplicate
def is_duplicates(list):
  for i in range(len(list)):
    item = list.pop()
    if item in list and item not in ('',None):
      return [True, item]
  return [False, None]

#check if the new addition to the roster is a duplicate to an existing user or name in the roster
@anvil.server.callable
def is_duplicate_addition_to_roster(scheduleID,newNurseName,userID):
  #check if the user is already in the roster
  isDuplicateUser = False
  r = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
  if r != None:
    isDuplicateUser = True
  #check if the name is already in the roster
  isDuplicateName = False
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = newNurseName)
  if r != None:
    isDuplicateName = True
  return [isDuplicateUser,isDuplicateName]

#returns a dictionary indicating t/f if the user is a scheduler, supervisor, OPT, FTE, CNA
@anvil.server.callable
def get_titles_dictionary(user):
  isSupervisor = user['supervisor_tf']
  isScheduler = user['scheduler_tf']
  fte = user['fte']
  return {'is_supervisor':isSupervisor,'is_scheduler':isScheduler,'fte':fte}
  
#initializes all the data on the Start page in a single server call.
#returns the user's fte and the data that they should see in the data grids on the start page
@anvil.server.callable
def initialize_start(user):
  userID = user['user_id']
  isSupervisor = user['supervisor_tf']
  isScheduler = user['scheduler_tf']
  isCharge = user['charge_tf']
  fte = user['fte']
  personalEmail = user['personal_email']
  hasAcceptedTerms = user['accepted_terms_tf']
  if isScheduler:
    schedulerGrid = show_schedules([True,False])
    rnGrid = None
    usersGrid = show_users()
  elif isSupervisor:
    schedulerGrid = None
    rnGrid = show_schedules([False])
    usersGrid = show_users()
  else:
    schedulerGrid = None
    rnGrid = show_schedules([False])
    usersGrid = None
  return [isScheduler,isSupervisor,fte,schedulerGrid,rnGrid,usersGrid,personalEmail,userID,isCharge,hasAcceptedTerms]

@anvil.server.callable
def initialize_roster(scheduleID,shouldGetCompleteList):
  usersDataIDs = get_roster_user_ids(scheduleID)
  usersData = show_users_for_roster(usersDataIDs)
  rosterData = show_roster(scheduleID)
  if shouldGetCompleteList:
    isCompleteList = is_marked_complete(scheduleID)
  else:
    isCompleteList = None
  cnaList = ['']
  fteList = ['']
  optList = ['']
  rnList = ['']
  for rosterRow in rosterData:
    fte = rosterRow['fte']
    nurseName = rosterRow['nurse_name']
    if fte == 'CNA':
      cnaList.append(nurseName)
    elif fte == 'OPT':
      optList.append(nurseName)
      rnList.append(nurseName)
    elif 'FTE' in fte:
      fteList.append(nurseName)
      rnList.append(nurseName)
  cnaList = sorted(cnaList)
  fteList = sorted(fteList)
  optList = sorted(optList)
  rnList = sorted(rnList)
  msgs = get_messages(scheduleID,'Request form',True)
  isUnreadMessages = msgs[1]
  return [usersData,rosterData,isCompleteList,cnaList,fteList,optList,rnList,isUnreadMessages]

@anvil.server.callable
def initialize_new_roster(scheduleStartDate):
  scheduleID = generate_schedule_id()
  add_schedule(scheduleID,scheduleStartDate)
  load_roster(scheduleID)
  return scheduleID

#initializes the supervisorform page
@anvil.server.callable
def initialize_supervisor_form(scheduleID):
  suggestedHolidays = get_suggested_holidays(scheduleID)
  holidaysData = show_holidays(scheduleID)
  ptoData = show_pto_data(scheduleID)
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  ptoHeaderFooter = sched['daystring_to_datestring']
  return [suggestedHolidays,holidaysData,ptoData,ptoHeaderFooter]

#initialize requests form
@anvil.server.callable
def initialize_requests(user,scheduleID):
  isRequestNeededSubmitted = is_request_needed_submitted(scheduleID,user)
  isRequestNeeded = isRequestNeededSubmitted[0]
  isRequestSubmitted = isRequestNeededSubmitted[1]
  fte = user['fte']
  userID = user['user_id']
  nurseName = user['name']
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  if 'FTE' in fte:
    personData = show_request_data(scheduleID,user)
    holidayData = sched['holiday_data']
    personData.insert(0,holidayData)
    personData = requestdata_to_bool(personData)
    sched = app_tables.schedules.get(schedule_id = scheduleID)
    requestsHeader = sched['daystring_to_datestring']
    optData = None
    optSubheaderText = None
  elif fte == 'OPT': 
    personData = None
    requestsHeader = None
    optData = show_opt_user(scheduleID,user)
    holidayData = app_tables.holidays.search(tables.order_by('holiday'),schedule_id = scheduleID)
    holidayDataLength = len(holidayData)
    scheduleName = sched['schedule']
    if holidayDataLength == 0:
      optSubheaderText = 'Select the dates you want to work ' + scheduleName
    elif holidayDataLength == 1:
      optSubheaderText = 'Select the dates you want to work ' + scheduleName + '. '
      hRow = holidayData[0]
      hDate = hRow['holiday']
      optSubheaderText += datetime.strptime(str(hDate),'%Y-%m-%d').strftime('%b %d, %Y') + ' is a holiday.'
    else:
      optSubheaderText = 'Select the dates you want to work ' + scheduleName + '. Holidays are '
      counter = 0
      for hRow in holidayData:
        counter += 1
        hDate = hRow['holiday']
        if counter == holidayDataLength:
          optSubheaderText += datetime.strptime(str(hDate),'%Y-%m-%d').strftime('%b %d, %Y') + '.'
        else:
          optSubheaderText += datetime.strptime(str(hDate),'%Y-%m-%d').strftime('%b %d, %Y') + ', '
  return [fte,isRequestNeeded,isRequestSubmitted,personData,requestsHeader,optData,optSubheaderText]

#if it's the first time visiting the demand form, it'll populate the demand table with all the dates
#in the scheduling period. Regardless, it will then return all the data in the demand table for the
#schedule as well as whether the demand step has been completed already
@anvil.server.callable
def initialize_demand(scheduleID):
  demandData = app_tables.demand.search(schedule_id = scheduleID)
  if len(demandData) == 0:
    nextDate = get_first_day(scheduleID)
    for i in range(30):
      dateStr = datetime.strptime(str(nextDate), '%Y-%m-%d').strftime('%b %d')
      app_tables.demand.add_row(
        schedule_id = scheduleID,
        demand_date = nextDate,
        demand_date_str = dateStr,
        demand = ''
      )
      if nextDate.weekday() == 4: #if it's a Friday
        nextDate += timedelta(days = 3)
      else:
        nextDate += timedelta(days = 1)
    demandData = app_tables.demand.search(schedule_id = scheduleID)
  isCompleteList = is_marked_complete(scheduleID)
  return [demandData,isCompleteList]

@anvil.server.callable
def initialize_cna(scheduleID):
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  dataHeader = sched['daystring_to_datestring']
  cnaData = app_tables.cna.search(schedule_id = scheduleID)
  isCompleteList = is_marked_complete(scheduleID)
  return [dataHeader, cnaData, isCompleteList]

@anvil.server.callable
def initialize_pat(scheduleID,sortString):
  patData = show_pat(scheduleID,sortString)
  isCompleteList = is_marked_complete(scheduleID)
  return [patData, isCompleteList]

@anvil.server.callable
def initialize_scheduler_input(scheduleID,user):
  messageData = get_messages(scheduleID,'Request form',True)
  holidayData = show_holidays(scheduleID)
  ptoData = show_pto(scheduleID,'name')
  offData = show_off(scheduleID,'name')
  shiftsData = show_shifts(scheduleID,'name')
  aclsData = show_acls(scheduleID,'name')
  optData = show_opt(scheduleID,'name')
  titles = get_titles_dictionary(user)
  isScheduler = titles['is_scheduler']
  isCompleteList = is_marked_complete(scheduleID)
  return [messageData,holidayData,ptoData,offData,shiftsData,aclsData,optData,isScheduler,isCompleteList]

@anvil.server.callable
def initialize_generate_schedule(scheduleID):
  instancesData = show_instances(scheduleID)
  instanceNameSuggestion = generate_instance_name_suggestion(scheduleID)
  return [instancesData,instanceNameSuggestion]

#returns a list of days (keys) that a given nurse has pto for a given schedule
@anvil.server.callable
def get_pto_days(scheduleID,userID):
  r = app_tables.pto2.get(schedule_id = scheduleID, user_id = userID)
  ptoDays = []
  for d in r:
    if r[d]:
      ptoDays.append(d)
  return ptoDays

@anvil.server.callable
def get_roster_user_ids(scheduleID):
  list = []
  for r in app_tables.roster.search(schedule_id = scheduleID):
    list.append(r['user_id'])
  return list

#This function is called with isAssembling = True when the scheduler is assembling the roster, and False when the user is later confirming the roster is correct 
@anvil.server.callable
def add_to_roster(scheduleID,userID,nurseName,nurseEmail,fte,startDate,isCharge,isAssembling):
  info = is_duplicate_addition_to_roster(scheduleID,nurseName,userID)
  isDuplicateUser = info[0]
  isDuplicateName = info[1]
  startDateStr = None
  if startDate not in ('',None):
    startDateStr = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
  if not isDuplicateUser and not isDuplicateName:
    app_tables.roster.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      nurse_email = nurseEmail,
      fte = fte,
      start_date = startDate,
      start_date_str = startDateStr,
      charge_tf = isCharge,
      added_datetime = datetime.now()
    )
    if not isAssembling:
      #Check included_in_roster_tf as True in the various tables
      #It's really intended for the case that the scheduler removes someone from the roster and then adds them back in, but it's okay if the user is brand new to the roster because this part will effectively do nothing
      #ACLS
      for r in app_tables.acls.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #CNA
      for r in app_tables.cna.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #OPT
      for r in app_tables.opt.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #OFF
      for r in app_tables.off.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #PAT
      for r in app_tables.pat.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #PTO
      for r in app_tables.pto.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
      #Shifts
      for r in app_tables.shiftsunavailable.search(schedule_id = scheduleID, user_id = userID):
        r['included_in_roster_tf'] = True
  rosterData = show_roster(scheduleID)
  usersDataIDs = get_roster_user_ids(scheduleID)
  usersDataIDs.append(userID)
  usersData = show_users_for_roster(usersDataIDs)
  return [isDuplicateUser,isDuplicateName,rosterData,usersData]

#Mark included_in_roster_tf as false so that the table rows aren't deleted but won't appear in the data grids
#It also DOES delete the row from the roster table
@anvil.server.callable
def exclude_from_schedule(row):
  scheduleID = row['schedule_id']
  userID = row['user_id']
  fte = row['fte']
  nurseName = row['nurse_name']
  #Remove from roster
  row.delete()
  #ACLS
  for r in app_tables.acls.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #CNA
  for r in app_tables.cna.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #OPT
  for r in app_tables.opt.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #OFF
  for r in app_tables.off.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #PAT
  for r in app_tables.pat.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #PTO
  for r in app_tables.pto.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  #Shifts
  for r in app_tables.shiftsunavailable.search(schedule_id = scheduleID, user_id = userID):
    r['included_in_roster_tf'] = False
  rosterData = show_roster(scheduleID)
  usersDataIDs = get_roster_user_ids(scheduleID)
  usersData = show_users_for_roster(usersDataIDs)
  return [rosterData, fte, nurseName, usersData]

#Accepts a string like 'day_1' and returns the associated datestring like 'Oct 07, 2022'
@anvil.server.callable
def daystring_to_datestring(scheduleID,dayString):
  calendarDictionary = get_calendar_dictionary(scheduleID)
  return calendarDictionary[dayString]

def daystring_to_date(scheduleID,dayString):
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleStartDate = sched['schedule_start_date']
  calendarDictionary = {
    'day_1': scheduleStartDate,
    'day_2': scheduleStartDate + timedelta(days = 3),
    'day_3': scheduleStartDate + timedelta(days = 4),
    'day_4': scheduleStartDate + timedelta(days = 5),
    'day_5': scheduleStartDate + timedelta(days = 6),
    'day_6': scheduleStartDate + timedelta(days = 7),
    'day_7': scheduleStartDate + timedelta(days = 10),
    'day_8': scheduleStartDate + timedelta(days = 11),
    'day_9': scheduleStartDate + timedelta(days = 12),
    'day_10': scheduleStartDate + timedelta(days = 13),
    'day_11': scheduleStartDate + timedelta(days = 14),
    'day_12': scheduleStartDate + timedelta(days = 17),
    'day_13': scheduleStartDate + timedelta(days = 18),
    'day_14': scheduleStartDate + timedelta(days = 19),
    'day_15': scheduleStartDate + timedelta(days = 20),
    'day_16': scheduleStartDate + timedelta(days = 21),
    'day_17': scheduleStartDate + timedelta(days = 24),
    'day_18': scheduleStartDate + timedelta(days = 25),
    'day_19': scheduleStartDate + timedelta(days = 26),
    'day_20': scheduleStartDate + timedelta(days = 27),
    'day_21': scheduleStartDate + timedelta(days = 28),
    'day_22': scheduleStartDate + timedelta(days = 31),
    'day_23': scheduleStartDate + timedelta(days = 32),
    'day_24': scheduleStartDate + timedelta(days = 33),
    'day_25': scheduleStartDate + timedelta(days = 34),
    'day_26': scheduleStartDate + timedelta(days = 35),
    'day_27': scheduleStartDate + timedelta(days = 38),
    'day_28': scheduleStartDate + timedelta(days = 39),
    'day_29': scheduleStartDate + timedelta(days = 40),
    'day_30': scheduleStartDate + timedelta(days = 41)
  }
  return calendarDictionary[dayString]

def date_to_daystring(scheduleID,date):
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleStartDate = sched['schedule_start_date']
  if date == scheduleStartDate:
    return 'day_1'
  elif date == scheduleStartDate + timedelta(days = 3):
    return 'day_2'
  elif date == scheduleStartDate + timedelta(days = 4):
    return 'day_3'
  elif date == scheduleStartDate + timedelta(days = 5):
    return 'day_4'
  elif date == scheduleStartDate + timedelta(days = 6):
    return 'day_5'
  elif date == scheduleStartDate + timedelta(days = 7):
    return 'day_6'
  elif date == scheduleStartDate + timedelta(days = 10):
    return 'day_7'
  elif date == scheduleStartDate + timedelta(days = 11):
    return 'day_8'
  elif date == scheduleStartDate + timedelta(days = 12):
    return 'day_9'
  elif date == scheduleStartDate + timedelta(days = 13):
    return 'day_10'
  elif date == scheduleStartDate + timedelta(days = 14):
    return 'day_11'
  elif date == scheduleStartDate + timedelta(days = 17):
    return 'day_12'
  elif date == scheduleStartDate + timedelta(days = 18):
    return 'day_13'
  elif date == scheduleStartDate + timedelta(days = 19):
    return 'day_14'
  elif date == scheduleStartDate + timedelta(days = 20):
    return 'day_15'
  elif date == scheduleStartDate + timedelta(days = 21):
    return 'day_16'
  elif date == scheduleStartDate + timedelta(days = 24):
    return 'day_17'
  elif date == scheduleStartDate + timedelta(days = 25):
    return 'day_18'
  elif date == scheduleStartDate + timedelta(days = 26):
    return 'day_19'
  elif date == scheduleStartDate + timedelta(days = 27):
    return 'day_20'
  elif date == scheduleStartDate + timedelta(days = 28):
    return 'day_21'
  elif date == scheduleStartDate + timedelta(days = 31):
    return 'day_22'
  elif date == scheduleStartDate + timedelta(days = 32):
    return 'day_23'
  elif date == scheduleStartDate + timedelta(days = 33):
    return 'day_24'
  elif date == scheduleStartDate + timedelta(days = 34):
    return 'day_25'
  elif date == scheduleStartDate + timedelta(days = 35):
    return 'day_26'
  elif date == scheduleStartDate + timedelta(days = 38):
    return 'day_27'
  elif date == scheduleStartDate + timedelta(days = 39):
    return 'day_28'
  elif date == scheduleStartDate + timedelta(days = 40):
    return 'day_29'
  elif date == scheduleStartDate + timedelta(days = 41):
    return 'day_30'
    
#Generates a unique schedule ID that's one bigger than the biggest schedule ID
@anvil.server.callable
def generate_schedule_id():
  biggestScheduleID = None
  for row in app_tables.schedules.search(tables.order_by('schedule_id',ascending=False)):
    biggestScheduleID = row['schedule_id']
    break
  if biggestScheduleID == None:
    return 1
  return biggestScheduleID + 1

#check if the given user is in the roster table
@anvil.server.callable
def is_in_roster(scheduleID,userID):
  r = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
  if r:
    return True
  return False

#get the first day of the schedule
@anvil.server.callable
def get_first_day(scheduleID):
  row = app_tables.schedules.get(schedule_id = scheduleID)
  return row['schedule_start_date']

#return text that suggests holidays for the schedule
def get_suggested_holidays(scheduleID):
  scheduleStartDate = get_first_day(scheduleID)
  date_1 = datetime.strptime(str(scheduleStartDate), '%Y-%m-%d')
  scheduleEndDate = date_1 + timedelta(days = 41)
  scheduleEndDate = scheduleEndDate.date()
  startYear = scheduleStartDate.year
  endYear = scheduleEndDate.year
  years = [startYear]
  if startYear != endYear:
    years.append(endYear)
  froedtertHolidays = [
    'New Year\'s Day',
    'Memorial Day',
    'Independence Day',
    'Labor Day',
    'Thanksgiving',
    'Christmas Day',
    'New Year\'s Day (Observed)',
    'Memorial Day (Observed)',
    'Independence Day (Observed)',
    'Labor Day (Observed)',
    'Thanksgiving (Observed)',
    'Christmas Day (Observed)'
  ]
  holidaysInSchedule = []
  for hol in holidays.US(years = years).items():
    holDate = hol[0]
    holName = hol[1]
    if scheduleStartDate <= holDate <= scheduleEndDate and holName in froedtertHolidays and holDate.weekday() <= 4:
      #if Froedtert observes the holiday during the schedule period, reformat it and return it
      holDate = datetime.strptime(str(holDate),'%Y-%m-%d').strftime('%b %-d')
      holidaysInSchedule.append(holDate)
  return holidaysInSchedule

#submitting roster means loading pto2, loading cna, sending an email to the supervisor, and updating the schedule status
@anvil.server.callable
def submit_roster(scheduleID,status):
  numRequestsNeeded = 0
  checkSubmitted = {} #a dictionary containing email: T/F pairs where it's true if the nurse bearing that email has submitted their request
  requestData = {} #a dictionary containing all the user's request inputs
  for row in app_tables.roster.search(
    schedule_id = scheduleID, 
    fte = q.any_of('OPT','CNA','FTE (1.0)','FTE (0.9)','FTE (0.8)','FTE (0.7)','FTE (0.6)','FTE (0.5)','FTE (0.4)','FTE (0.3)','FTE (0.2)','FTE (0.1)')
  ):
    userIDStr = str(row['user_id'])
    fte = row['fte']
    if fte != 'CNA':
      numRequestsNeeded += 1
      checkSubmitted[userIDStr] = 'False'
    if fte != 'OPT':
      requestData[userIDStr] = []
  #update schedules table
  r = app_tables.schedules.get(schedule_id = scheduleID)
  r['check_submitted'] = checkSubmitted
  r['requests_needed'] = numRequestsNeeded
  r['requests_submitted'] = 0
  #initialize request data
  initialize_request_data(scheduleID,requestData,r)
  #load cna table
  load_cna(scheduleID)
  #pass the torch to the supervisor
  send_pto_email()
  update_schedule_status(scheduleID,status)

@anvil.server.callable
def get_new_instance_id(scheduleID):
  biggestInstanceID = None
  for row in app_tables.instances.search(tables.order_by('instance_id',ascending = False), schedule_id = scheduleID):
    biggestInstanceID = row['instance_id']
    break
  if biggestInstanceID == None:
    return 1
  else:
    return biggestInstanceID + 1

@anvil.server.callable
def generate_instance_name_suggestion(scheduleID):
  return 'Schedule ' + str(get_new_instance_id(scheduleID))

@anvil.server.callable
def get_csv(scheduleID,instanceID):
  csvFile = StringIO(newline='')
  writer = csv.writer(csvFile, delimiter = ',')
  header1 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'header1')
  header2 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'header2')
  footer1 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer1')
  footer2 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer2')
  footer3 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer3')
  footer5 = app_tables.generatedschedules.search(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer5')
  data = app_tables.generatedschedules.search(schedule_id = scheduleID, instance_id = instanceID, row_type = 'data')
  data = sorted(data, key = lambda x: (x['fte_sortable'],x['nurse_names']))
  csvData = [header1, header2]
  for dataRow in data:
    csvData.append(dataRow)
  csvData.append(footer1)
  csvData.append(footer2)
  csvData.append(footer3)
  for footerRow in footer5:
    csvData.append(footerRow)
  for csvDataRow in csvData:
    writer.writerow(
      [
        csvDataRow['nurse_names'],
        csvDataRow['fte'],
        csvDataRow['day_1'],
        csvDataRow['day_2'],
        csvDataRow['day_3'],
        csvDataRow['day_4'],
        csvDataRow['day_5'],
        csvDataRow['day_6'],
        csvDataRow['day_7'],
        csvDataRow['day_8'],
        csvDataRow['day_9'],
        csvDataRow['day_10'],
        csvDataRow['nurse_names_2'],
        csvDataRow['day_11'],
        csvDataRow['day_12'],
        csvDataRow['day_13'],
        csvDataRow['day_14'],
        csvDataRow['day_15'],
        csvDataRow['day_16'],
        csvDataRow['day_17'],
        csvDataRow['day_18'],
        csvDataRow['day_19'],
        csvDataRow['day_20'],
        csvDataRow['nurse_names_3'],
        csvDataRow['day_21'],
        csvDataRow['day_22'],
        csvDataRow['day_23'],
        csvDataRow['day_24'],
        csvDataRow['day_25'],
        csvDataRow['day_26'],
        csvDataRow['day_27'],
        csvDataRow['day_28'],
        csvDataRow['day_29'],
        csvDataRow['day_30'],
        csvDataRow['nurse_names_4']
      ]
    )
  csvFile.seek(0)
  scheduleStartDate = get_first_day(scheduleID)
  scheduleStartDate = datetime.strptime(str(scheduleStartDate),'%Y-%m-%d').strftime('%m-%d')
  fileName = 'schedule_' + str(scheduleStartDate) + '.csv'
  media_obj = anvil.BlobMedia('csv', csvFile.read().encode(), name=fileName)
  return media_obj

@anvil.server.callable
def publish_schedule(scheduleID,instanceID):
  #update schedule status
  update_schedule_status(scheduleID,'Completed')
  #send email notification to the nurses that the schedule is ready
  supervisorsAndSchedulers = get_supervisors_and_schedulers()
  supervisors = supervisorsAndSchedulers[0] #supervisors list
  schedulers = supervisorsAndSchedulers[1] #schedulers list
  toList = []
  for r in app_tables.roster.search(schedule_id = scheduleID):
    toList.append(r['nurse_email'])
  for x in supervisors:
    if x not in toList:
      toList.append(x)
  for x in schedulers:
    if x not in toList:
      toList.append(x)
  for user in app_tables.users.search(email = q.any_of(*toList)):
    personalEmail = user['personal_email']
    if personalEmail not in ('',None):
      toList.append(personalEmail)
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleName = sched['schedule']
  anvil.email.send(
    from_name = 'Tachy',
    to = toList,
    subject = "[Schedule] Done & ready to view!",
    text = 'Hey!' + '\n \n' + 'The ' + scheduleName + ' schedule is ready. Log in to view and interact with the schedule.',
    html = 'Hey!' + '\n \n' + 'The ' + scheduleName + ' schedule is ready. <a href="https://fsc.tachy.app">Log in</a> to view and interact with the schedule.'
  )
  #update instances table
  update_instance_status(scheduleID,instanceID,'Published')
  #update schedules table to populate its completed_instance_id column
  r = app_tables.schedules.get(schedule_id = scheduleID)
  update_schedule(r,'completed_instance_id',instanceID)

#accepts a row in the instances table
#returns the schedule_id and instance_id values for that row
@anvil.server.callable
def get_instance_ids(instancesRow):
  return [instancesRow['schedule_id'], instancesRow['instance_id']]

def is_active_fill(scheduleID,instanceID,requesterID,dayString):
  r = app_tables.fill.get(schedule_id = scheduleID, instance_id = instanceID, requester_user_id = requesterID, day_string = dayString, request_active_tf = True)
  if r == None:
    return [False, None]
  else:
    fillID = r['fill_id']
    return [True, fillID]

def is_active_swap(scheduleID,instanceID,requesterID,dayString):
  r = app_tables.swap.get(schedule_id = scheduleID, instance_id = instanceID, requester_user_id = requesterID, requester_day_string = dayString, request_active_tf = True)
  if r == None:
    return [False, None]
  else:
    swapID = r['swap_id']
    return [True, swapID]

@anvil.server.callable
def add_plus_seven_shift(scheduleID,instanceID,user,row,dayString,value):
  isDeclinedFill = False
  userID = user['user_id']
  #get any fills someone else has requested this user to fill
  fillRequestsReceived = []
  for recipient in app_tables.fillrecipients.search(schedule_id = scheduleID, instance_id = instanceID, recipient_user_id = userID, recipient_requested_tf = True, response = q.any_of(None,'')):
    fillID = recipient['fill_id']
    fill = app_tables.fill.get(fill_id = fillID)
    isActiveFill = fill['request_active_tf']
    requestedDayString = fill['day_string']
    if isActiveFill and requestedDayString == dayString:
      decline_fill(fillID,user,dayString)
      isDeclinedFill = True
  update_schedule(row,dayString,value)
  return isDeclinedFill

#check to see if every recipient has declined the fill request
def is_all_declined_fill(fillID):
  for recipient in app_tables.fillrecipients.search(fill_id = fillID, recipient_requested_tf = True):
    if recipient['response'] != 'declined':
      return False
  return True

@anvil.server.callable
def decline_fill(fillID,user,dayString):
  #check if the fill is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the fill to no longer be active, in which case, taking this action should do nothing
  isActive = False
  fill = app_tables.fill.get(fill_id = fillID)
  if fill['request_active_tf']:
    isActive = True
    recipientID = user['user_id']
    #update recipient status to declined
    recipient = app_tables.fillrecipients.get(fill_id = fillID, recipient_user_id = recipientID)
    recipient['response'] = 'declined'
    #check to see if everyone has declined or if there are still some who can accept the fill request
    isAllDeclined = is_all_declined_fill(fillID)
    if isAllDeclined:
      #update fill active status to false
      fill['request_active_tf'] = False
      #email the requester to let them know their request has been declined by everyone
      requesterEmail = fill['requester_email']
      scheduleID = fill['schedule_id']
      requestDateStr = daystring_to_datestring(scheduleID,dayString)
      user = app_tables.users.get(email = requesterEmail)
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toList = [requesterEmail, personalEmail]
      else:
        toList = requesterEmail
      anvil.email.send(
        from_name = 'Tachy',
        to = toList,
        subject = "[Schedule] Your fill request is declined",
        text = 'Hey!' + '\n \n' + 'Your request for someone to fill your shift on ' + requestDateStr + ' has been declined by everyone you sent a request to. \n \n If you\'d like, you can log in to  (1) request another fill, or (2) request a swap.',
        html = 'Hey!' + '\n \n' + 'Your request for someone to fill your shift on ' + requestDateStr + ' has been declined by everyone you sent a request to. \n \n If you\'d like, you can <a href="https://fsc.tachy.app">log in</a> to (1) request another fill, or (2) request a swap.'
      )
  return isActive

@anvil.server.callable
def accept_fill(fillID,user,dayString):
  #check if the fill is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the fill to no longer be active, in which case, taking this action should do nothing
  isActive = False
  fill = app_tables.fill.get(fill_id = fillID)
  if fill['request_active_tf']:
    isActive = True
    userID = user['user_id']
    #update recipient status to accepted
    recipient = app_tables.fillrecipients.get(fill_id = fillID, recipient_user_id = userID)
    recipient['response'] = 'accepted'
    #update fill active status to false
    fill['request_active_tf'] = False
    #update generated schedule
    scheduleID = fill['schedule_id']
    instanceID = fill['instance_id']
    requesterID = fill['requester_user_id']
    recipientRow = app_tables.generatedschedules.get(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data',user_id = userID)
    requesterRow = app_tables.generatedschedules.get(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data',user_id = requesterID)
    shiftValue = requesterRow[dayString]
    recipientRow[dayString] = shiftValue
    requesterRow[dayString] = ''
    #send email notification to all requested recipients who haven't declined as well as to the requester
    toAddressList = []
    requesterEmail = fill['requester_email']
    requesterName = fill['requester_name']
    recipientName = recipient['recipient_name']
    requestDateStr = daystring_to_datestring(scheduleID,dayString)
    for r in app_tables.fillrecipients.search(fill_id = fillID, recipient_requested_tf = True, response = q.not_('declined')):
      toAddressList.append(r['recipient_email'])
    for user in app_tables.users.search(email = q.any_of(*toAddressList)):
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toAddressList.append(personalEmail)
    anvil.email.send(
      from_name = 'Tachy',
      to = toAddressList,
      cc = requesterEmail,
      subject = "[Schedule] Fill request accepted",
      text = 'Hey!' + '\n \n' + recipientName + ' accepted ' + requesterName + '\'s request to fill their shift on ' + requestDateStr + '. The fill request is now closed.'
    )
    updatedSched = app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data')
    updatedSched = sorted(updatedSched, key = lambda x: (x['fte'],x['nurse_names']))
    return [isActive, updatedSched]
  else:
    return [isActive, None]
  
@anvil.server.callable
def cancel_fill(fillID):
  #check if the fill is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the fill to no longer be active, in which case, taking this action should do nothing
  isActive = False
  r = app_tables.fill.get(fill_id = fillID)
  if r['request_active_tf']:
    isActive = True
    #Set fill active status to false
    r['request_active_tf'] = False
    #send email notification to all requested recipients who haven't declined as well as to the requester
    scheduleID = r['schedule_id']
    dayString = r['day_string']
    requesterEmail = r['requester_email']
    requesterName = r['requester_name']
    requestDateStr = daystring_to_datestring(scheduleID,dayString)
    toAddressList = []
    for r in app_tables.fillrecipients.search(fill_id = fillID, recipient_requested_tf = True, response = q.not_('declined')):
      toAddressList.append(r['recipient_email'])
    for user in app_tables.users.search(email = q.any_of(*toAddressList)):
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toAddressList.append(personalEmail)
    anvil.email.send(
      from_name = 'Tachy',
      to = toAddressList,
      cc = requesterEmail,
      subject = "[Schedule] Fill request canceled",
      text = 'Hey!' + '\n \n' + 'Just letting you know that ' + requesterName + ' canceled their request to fill their shift on ' + requestDateStr + '. \n \n No further action required.'
    )
  return isActive

@anvil.server.callable
def submit_fill_request(fillID):
  #update fill active status to True
  fill = app_tables.fill.get(fill_id = fillID)
  fill['request_active_tf'] = True
  #send email to the recipients
  requesterName = fill['requester_name']
  requesterEmail = fill['requester_email']
  scheduleID = fill['schedule_id']
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleName = sched['schedule']
  dayString = fill['day_string']
  requestDateStr = daystring_to_datestring(scheduleID,dayString)
  toAddressList = []
  for r in app_tables.fillrecipients.search(fill_id = fillID, recipient_requested_tf = True):
    toAddressList.append(r['recipient_email'])
  for user in app_tables.users.search(email = q.any_of(*toAddressList)):
    personalEmail = user['personal_email']
    if personalEmail not in ('',None):
      toAddressList.append(user['personal_email'])
  anvil.email.send(
    from_name = 'Tachy',
    to = toAddressList,
    cc = requesterEmail,
    subject = "[Schedule] Fill my shift?",
    text = 'Hey!' + '\n \n' + requesterName + ' has requested you to fill their shift on ' + requestDateStr + '. \n \n Log in, and click on the ' + scheduleName + ' schedule to accept or decline.',
    html = 'Hey!' + '\n \n' + requesterName + ' has requested you to fill their shift on ' + requestDateStr + '. \n \n <a href="https://fsc.tachy.app">Log in</a>, and click on the ' + scheduleName + ' schedule to accept or decline.'
  )

@anvil.server.callable
def submit_swap_request(swapID):
  #update swap active status to True
  swap = app_tables.swap.get(swap_id = swapID)
  swap['request_active_tf'] = True
  #send email to the recipients
  requesterName = swap['requester_name']
  requesterEmail = swap['requester_email']
  scheduleID = swap['schedule_id']
  dayString = swap['requester_day_string']
  requestDateStr = daystring_to_datestring(scheduleID,dayString)
  requesterShift = swap['requester_shift']
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleName = sched['schedule']
  toAddressList = []
  for recipient in app_tables.swaprecipients.search(swap_id = swapID,recipient_requested_tf = True):
    toAddressList.append(recipient['recipient_email'])
  for user in app_tables.users.search(email = q.any_of(*toAddressList)):
    personalEmail = user['personal_email']
    if personalEmail not in ('',None):
      toAddressList.append(personalEmail)
  anvil.email.send(
    from_name = 'Tachy',
    to = toAddressList,
    cc = requesterEmail,
    subject = "[Schedule] Swap shifts?",
    text = 'Hey!' + '\n \n' + requesterName + ' has requested to swap shifts with you. \n \n Log in, and click on the ' + scheduleName + ' schedule to accept or decline.',
    html = 'Hey!' + '\n \n' + requesterName + ' has requested to swap shifts with you. \n \n <a href="https://fsc.tachy.app">Log in</a>, and click on the ' + scheduleName + ' schedule to accept or decline.'
  )

@anvil.server.callable
def cancel_swap(swapID):
  #check if the swap is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the swap to no longer be active, in which case, canceling this swap should do nothing
  isActive = False
  swap = app_tables.swap.get(swap_id = swapID)
  if swap['request_active_tf']:
    isActive = True
    #Set swap active status to false
    swap['request_active_tf'] = False
    #send email notification to all requested recipients who haven't declined as well as to the requester
    requesterEmail = swap['requester_email']
    requesterName = swap['requester_name']
    scheduleID = swap['schedule_id']
    dayString = swap['requester_day_string']
    requesterDateStr = daystring_to_datestring(scheduleID,dayString)
    toAddressList = []
    for recipient in app_tables.swaprecipients.search(swap_id = swapID, recipient_requested_tf = True, response = q.not_('declined')):
      toAddressList.append(recipient['recipient_email'])
    for user in app_tables.users.search(email = q.any_of(*toAddressList)):
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toAddressList.append(personalEmail)
    anvil.email.send(
      from_name = 'Tachy',
      to = toAddressList,
      cc = requesterEmail,
      subject = "[Schedule] Swap request canceled",
      text = 'Hey!' + '\n \n' + 'Just letting you know that ' + requesterName + ' canceled their request to swap for their shift on ' + requesterDateStr + '. No further action required.'
    )
  return isActive

def handle_affected_swaps(originalSwapID,scheduleID,instanceID,requesterUser,requesterID,recipientUser,requesterDayString,recipientDayString):
  recipientID = recipientUser['user_id']
  #1. Look at recipient. See if they are the recipient of any other active swaps of the same recipient day string they accepted. If so, decline. Example: if both nurse 1 and nurse 2 request a swap for nurse 3 to move away from Oct 7, and nurse 3 accepts nurse 1, then it should automatically decline nurse 2's swap request.
  for r in app_tables.swaprecipients.search(recipient_user_id = recipientID, recipient_day_string = recipientDayString, recipient_requested_tf = True, response = q.not_('declined')):
    swapID = r['swap_id']
    swap = app_tables.swap.get(swap_id = swapID)
    if swap['request_active_tf'] and swapID != originalSwapID:
      sourceDayString = swap['requester_day_string']
      decline_swap(swapID,recipientUser,sourceDayString,recipientDayString)

  #2. Look at recipient. See if they requested any swaps or fills on the original day they were scheduled before the swap. If so, cancel the request.
  ##fills
  fill = app_tables.fill.get(schedule_id = scheduleID,instance_id = instanceID, requester_user_id = recipientID, day_string = recipientDayString, request_active_tf = True)
  if fill != None:
    fillID = fill['fill_id']
    cancel_fill(fillID)
  ##swaps
  swap = app_tables.swap.get(schedule_id = scheduleID,instance_id = instanceID,requester_user_id = recipientID, requester_day_string = recipientDayString, request_active_tf = True)
  if swap != None:
    swapID = swap['swap_id']
    cancel_swap(swapID)

  #3. Look at requester. See if they have any other requests where they want to swap to the date they just swapped to. If so, make recipient_requested_tf false for every recipient on that day for that swap. If every recipient requested tf is false for that swap, then cancel the swap.
  for s in app_tables.swap.search(schedule_id = scheduleID, instance_id = instanceID, requester_user_id = requesterID, request_active_tf = True):
    swapID = s['swap_id']
    for r in app_tables.swaprecipients.search(swap_id = swapID, recipient_day_string = recipientDayString, recipient_requested_tf = True, response = q.not_('declined')):
      r['recipient_requested_tf'] = False
    rows = app_tables.swaprecipients.search(swap_id = swapID, recipient_requested_tf = True, response = q.not_('declined'))
    if len(rows) == 0: #if nobody can accept/decline the swap anymore because you just set recipient_requested_tf to False for every recipient of the swap...
      cancel_swap(swapID)

  #4. Look at requester. See if they are the recipient of any swaps to the day they just swapped from. If so, decline.
  for r in app_tables.swaprecipients.search(schedule_id = scheduleID,instance_id = instanceID,recipient_user_id = requesterID,recipient_day_string = requesterDayString,recipient_requested_tf = True, response = q.not_('declined')):
    swapID = r['swap_id']
    swap = app_tables.swap.get(swap_id = swapID)
    if swap['request_active_tf'] and swapID != originalSwapID:
      sourceDayString = swap['requester_day_string']
      decline_swap(swapID,requesterUser,sourceDayString,requesterDayString)

@anvil.server.callable
def accept_swap(swapID,user,requesterDayString,recipientDayString):
  #check if the swap is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the swap to no longer be active, in which case, accepting this swap should do nothing
  isActive = False
  swap = app_tables.swap.get(swap_id = swapID)
  if swap['request_active_tf']:
    isActive = True
    #update swap active status to false
    swap['request_active_tf'] = False
    #handle complex swap situations (e.g. the recipient had multiple swaps to choose from, so the one they didn't choose must be automatically declined. + other hairy situations)
    scheduleID = swap['schedule_id']
    instanceID = swap['instance_id']
    requesterID = swap['requester_user_id']
    requesterUser = app_tables.users.get(user_id = requesterID)
    handle_affected_swaps(swapID,scheduleID,instanceID,requesterUser,requesterID,user,requesterDayString,recipientDayString)
    #update recipient status to accepted
    userID = user['user_id']
    recipient = app_tables.swaprecipients.get(swap_id = swapID, recipient_user_id = userID, recipient_day_string = recipientDayString)
    recipient['response'] = 'accepted'
    #update generated schedule
    requesterID = swap['requester_user_id']
    recipientRow = app_tables.generatedschedules.get(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data',user_id = userID)
    requesterRow = app_tables.generatedschedules.get(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data',user_id = requesterID)
    requesterShift = requesterRow[requesterDayString]
    recipientShift = recipientRow[recipientDayString]
    recipientRow[recipientDayString] = ''
    requesterRow[recipientDayString] = recipientShift
    recipientRow[requesterDayString] = requesterShift
    requesterRow[requesterDayString] = ''
    #send email notification to all requested recipients who haven't declined as well as to the requester
    toAddressList = []
    requesterEmail = swap['requester_email']
    requesterName = swap['requester_name']
    recipientName = recipient['recipient_name']
    requestDateStr = daystring_to_datestring(scheduleID,requesterDayString)
    recipientDateStr = daystring_to_datestring(scheduleID, recipientDayString)
    for r in app_tables.swaprecipients.search(swap_id = swapID, recipient_requested_tf = True, response = q.not_('declined')):
      toAddressList.append(r['recipient_email'])
    for user in app_tables.users.search(email = q.any_of(*toAddressList)):
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toAddressList.append(personalEmail)
    anvil.email.send(
      from_name = 'Tachy',
      to = toAddressList,
      cc = requesterEmail,
      subject = "[Schedule] Swap request accepted",
      text = 'Hey!' + '\n \n' + recipientName + ' accepted ' + requesterName + '\'s swap request.' + '\n \n' + 'Now, ' + recipientName + ' will work on ' + requestDateStr + ', and ' + requesterName + ' will work on ' + recipientDateStr + '.'
    )
  return isActive

#check to see if every recipient has declined the swap request
def is_all_declined_swap(swapID):
  for recipient in app_tables.swaprecipients.search(swap_id = swapID, recipient_requested_tf = True):
    if recipient['response'] != 'declined':
      return False
  return True

@anvil.server.callable
def decline_swap(swapID,user,requesterDayString,recipientDayString):
  #check if the swap is still active. if so, run the code. if not, return that it's false. It would be inactive if the user load the page and sees the accept button when another user does an action that causes the swap to no longer be active, in which case, declining this swap should do nothing
  isActive = False
  swap = app_tables.swap.get(swap_id = swapID)
  if swap['request_active_tf']:
    isActive = True
    recipientID = user['user_id']
    #update recipient status to declined
    recipient = app_tables.swaprecipients.get(swap_id = swapID, recipient_user_id = recipientID, recipient_day_string = recipientDayString)
    recipient['response'] = 'declined'
    #check to see if everyone has declined or if there are still some who can accept the swap request
    isAllDeclined = is_all_declined_swap(swapID)
    if isAllDeclined:
      #update swap active status to false
      swap['request_active_tf'] = False
      #email the requester to let them know their request has been declined by everyone
      requesterEmail = swap['requester_email']
      scheduleID = swap['schedule_id']
      requestDateStr = daystring_to_datestring(scheduleID,requesterDayString)
      user = app_tables.users.get(email = requesterEmail)
      personalEmail = user['personal_email']
      if personalEmail not in ('',None):
        toList = [requesterEmail, user['personal_email']]
      else:
        toList = requesterEmail
      anvil.email.send(
        from_name = 'Tachy',
        to = toList,
        subject = "[Schedule] Your swap request is declined",
        text = 'Hey!' + '\n \n' + 'Your request for someone to swap for your shift on ' + requestDateStr + ' has been declined by everyone you sent a request to. \n \n If you\'d like, you can log in to (1) request another swap, or (2) request a fill.',
        html = 'Hey!' + '\n \n' + 'Your request for someone to swap for your shift on ' + requestDateStr + ' has been declined by everyone you sent a request to. \n \n If you\'d like, you can <a href="https://fsc.tachy.app">log in</a> to (1) request another swap, or (2) request a fill.'
      )
  return isActive

def get_daily_backup_late(scheduleID,instanceID):
  backupLate = {'day_1': 0,'day_2': 0,'day_3': 0,'day_4': 0,'day_5': 0,'day_6': 0,'day_7': 0,'day_8': 0,'day_9': 0,'day_10': 0,'day_11': 0,'day_12': 0,'day_13': 0,'day_14': 0,'day_15': 0,'day_16': 0,'day_17': 0,'day_18': 0,'day_19': 0,'day_20': 0,'day_21': 0,'day_22': 0,'day_23': 0,'day_24': 0,'day_25': 0,'day_26': 0,'day_27': 0,'day_28': 0,'day_29': 0,'day_30': 0}
  for g in app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID, row_type = 'data'):
    for dayString in backupLate:
      if g[dayString] in ('7*','7*-C'):
        backupLate[dayString] += 1
  return backupLate

#accepts fte, and returns the maximum number of Mondays and Fridays that nurse should work
def get_max_mf_worked(fte):
  maxMF = 12
  if fte == 0.9:
    maxMF = 11
  elif fte == 0.8:
    maxMF = 10
  elif fte == 0.7:
    maxMF = 9
  elif fte == 0.6:
    maxMF = 8
  elif fte == 0.5:
    maxMF = 6
  elif fte == 0.4:
    maxMF = 6
  elif fte == 0.3:
    maxMF = 4
  elif fte == 0.2:
    maxMF = 3
  elif fte == 0.1:
    maxMF = 2
  return maxMF

def get_max_fri_worked(fte):
  maxF = 6
  if fte in (0.8,0.7):
    maxF = 5
  elif fte == 0.6:
    maxF = 4
  elif fte in (0.5,0.4):
    maxF = 3
  elif fte in (0.3,0.2):
    maxF = 2
  elif fte == 0.1:
    maxF = 1
  return maxF

@anvil.server.callable
def refresh_instance_stats(scheduleID,instanceID,typeFilter,nameFilter,targetFilter,sortString):
  update_instance_stats(scheduleID,instanceID)
  instanceStatsData = show_instance_stats(scheduleID,instanceID,typeFilter,nameFilter,targetFilter,sortString)
  return instanceStatsData

@anvil.server.callable
def update_instance_stats(scheduleID,instanceID):
  instance = app_tables.instances.get(schedule_id = scheduleID, instance_id = instanceID)
  instanceStats = instance['instance_stats']
  dayStrings = ['day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10','day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20','day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30']
  dayStringsPP1 = ['day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10']
  dayStringsPP2 = ['day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20']
  dayStringsPP3 = ['day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30']
  dayStringsWW1 = ['day_2','day_3','day_4','day_5','day_6']
  dayStringsWW2 = ['day_7','day_8','day_9','day_10','day_11']
  dayStringsWW3 = ['day_12','day_13','day_14','day_15','day_16']
  dayStringsWW4 = ['day_17','day_18','day_19','day_20','day_21']
  dayStringsWW5 = ['day_22','day_23','day_24','day_25','day_26']
  dayStringsWW6 = ['day_27','day_28','day_29','day_30']
  dayStringsMondaysFridays = ['day_1','day_2','day_6','day_7','day_11','day_12','day_16','day_17','day_21','day_22','day_26','day_27']
  dayStringsFridays = ['day_1','day_6','day_11','day_16','day_21','day_26']
  numEarlyDict = {'day_1': 0,'day_2': 0,'day_3': 0,'day_4': 0,'day_5': 0,'day_6': 0,'day_7': 0,'day_8': 0,'day_9': 0,'day_10': 0,'day_11': 0,'day_12': 0,'day_13': 0,'day_14': 0,'day_15': 0,'day_16': 0,'day_17': 0,'day_18': 0,'day_19': 0,'day_20': 0,'day_21': 0,'day_22': 0,'day_23': 0,'day_24': 0,'day_25': 0,'day_26': 0,'day_27': 0,'day_28': 0,'day_29': 0,'day_30': 0}
  numBackupDict = {'day_1': 0,'day_2': 0,'day_3': 0,'day_4': 0,'day_5': 0,'day_6': 0,'day_7': 0,'day_8': 0,'day_9': 0,'day_10': 0,'day_11': 0,'day_12': 0,'day_13': 0,'day_14': 0,'day_15': 0,'day_16': 0,'day_17': 0,'day_18': 0,'day_19': 0,'day_20': 0,'day_21': 0,'day_22': 0,'day_23': 0,'day_24': 0,'day_25': 0,'day_26': 0,'day_27': 0,'day_28': 0,'day_29': 0,'day_30': 0}
  numLateDict = {'day_1': 0,'day_2': 0,'day_3': 0,'day_4': 0,'day_5': 0,'day_6': 0,'day_7': 0,'day_8': 0,'day_9': 0,'day_10': 0,'day_11': 0,'day_12': 0,'day_13': 0,'day_14': 0,'day_15': 0,'day_16': 0,'day_17': 0,'day_18': 0,'day_19': 0,'day_20': 0,'day_21': 0,'day_22': 0,'day_23': 0,'day_24': 0,'day_25': 0,'day_26': 0,'day_27': 0,'day_28': 0,'day_29': 0,'day_30': 0}
  numChargeDict = {'day_1': 0,'day_2': 0,'day_3': 0,'day_4': 0,'day_5': 0,'day_6': 0,'day_7': 0,'day_8': 0,'day_9': 0,'day_10': 0,'day_11': 0,'day_12': 0,'day_13': 0,'day_14': 0,'day_15': 0,'day_16': 0,'day_17': 0,'day_18': 0,'day_19': 0,'day_20': 0,'day_21': 0,'day_22': 0,'day_23': 0,'day_24': 0,'day_25': 0,'day_26': 0,'day_27': 0,'day_28': 0,'day_29': 0,'day_30': 0}
  #Get stats so you can update instancestats right here for nurse name types and slightly further down for day types
  for g in app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID, row_type = 'data'):
    fte = g['fte']
    #stats for #Early/Backup Late/Late/Charge Shifts
    for dayString in dayStrings:
      if g[dayString] == '6':
        numEarlyDict[dayString] += 1
      elif g[dayString] == '6-C':
        numEarlyDict[dayString] += 1
        numChargeDict[dayString] += 1
      elif g[dayString] == '7-C':
        numChargeDict[dayString] += 1
      elif g[dayString] == '7*':
        numBackupDict[dayString] += 1
      elif g[dayString] == '7*-C':
        numBackupDict[dayString] += 1
        numChargeDict[dayString] += 1
      elif g[dayString] == '8':
        numLateDict[dayString] += 1
      elif g[dayString] == '8-C':
        numLateDict[dayString] += 1
        numChargeDict[dayString] += 1
    if fte not in ('OPT','ORIENT'):
      #Get stat for # Days Scheduled PP 1/2/3 for this nurse
      nurseName = g['nurse_names']
      fte = float(fte)
      numDaysAssignedPP1 = 0
      numDaysAssignedPP2 = 0
      numDaysAssignedPP3 = 0
      for dayString in dayStringsPP1:
        shift = g[dayString]
        if shift not in ('',None,'Off'):
          numDaysAssignedPP1 += 1
      for dayString in dayStringsPP2:
        shift = g[dayString]
        if shift not in ('',None,'Off'):
          numDaysAssignedPP2 += 1
      for dayString in dayStringsPP3:
        shift = g[dayString]
        if shift not in ('',None,'Off'):
          numDaysAssignedPP3 += 1
      #update # Days Scheduled PP1 for this nurse
      key = '# Days Scheduled PP1;' + nurseName
      row = instanceStats[key]
      row['stat'] = numDaysAssignedPP1
      target = row['stat_target']
      if numDaysAssignedPP1 == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #update # Days Scheduled PP2 for this nurse
      key = '# Days Scheduled PP2;' + nurseName
      row = instanceStats[key]
      row['stat'] = numDaysAssignedPP2
      target = row['stat_target']
      if numDaysAssignedPP2 == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #update # Days Scheduled PP3 for this nurse
      key = '# Days Scheduled PP3;' + nurseName
      row = instanceStats[key]
      row['stat'] = numDaysAssignedPP3
      target = row['stat_target']
      if numDaysAssignedPP3 == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Workweeks Overloaded for this nurse
      if fte >= 0.9:
        maxWW = 5
      elif fte >= 0.7:
        maxWW = 4
      elif fte >= 0.5:
        maxWW = 3
      elif fte >= 0.3:
        maxWW = 2
      else:
        maxWW = 1
      numWorkweeksOverloaded = 0
      dayStringsWorkweeks = [dayStringsWW1,dayStringsWW2,dayStringsWW3,dayStringsWW4,dayStringsWW5,dayStringsWW6]
      for x in dayStringsWorkweeks:
        numDaysAssigned = 0
        for dayString in x:
          if g[dayString] not in ('',None,'Off','PTO','H'):
            numDaysAssigned += 1
        if numDaysAssigned > maxWW:
          numWorkweeksOverloaded += 1
      #Update # Workweeks Overloaded for this nurse
      key = '# Workweeks Overloaded;' + nurseName
      row = instanceStats[key]
      row['stat'] = numWorkweeksOverloaded
      target = row['stat_target']
      if numWorkweeksOverloaded == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stats for # 6/7*/8/charge Shifts and # 6/7*/8/charge Shifts PP1/2/3
      numEarly = 0
      numEarlyPP1 = 0
      numEarlyPP2 = 0
      numEarlyPP3 = 0
      numBackup = 0
      numBackupPP1 = 0
      numBackupPP2 = 0
      numBackupPP3 = 0
      numLate = 0
      numLatePP1 = 0
      numLatePP2 = 0
      numLatePP3 = 0
      numCharge = 0
      numChargePP1 = 0
      numChargePP2 = 0
      numChargePP3 = 0
      for dayString in dayStringsPP1:
        if g[dayString] == '6':
          numEarlyPP1 += 1
        elif g[dayString] == '6-C':
          numEarlyPP1 += 1
          numChargePP1 += 1
        elif g[dayString] == '7*':
          numBackupPP1 += 1
        elif g[dayString] == '7*-C':
          numBackupPP1 += 1
          numChargePP1 += 1
        elif g[dayString] == '8':
          numLatePP1 += 1
        elif g[dayString] == '8-C':
          numLatePP1 += 1
          numChargePP1 += 1
        elif g[dayString] == '7-C':
          numChargePP1 += 1
      for dayString in dayStringsPP2:
        if g[dayString] == '6':
          numEarlyPP2 += 1
        elif g[dayString] == '6-C':
          numEarlyPP2 += 1
          numChargePP2 += 1
        elif g[dayString] == '7*':
          numBackupPP2 += 1
        elif g[dayString] == '7*-C':
          numBackupPP2 += 1
          numChargePP2 += 1
        elif g[dayString] == '8':
          numLatePP2 += 1
        elif g[dayString] == '8-C':
          numLatePP2 += 1
          numChargePP2 += 1
        elif g[dayString] == '7-C':
          numChargePP2 += 1
      for dayString in dayStringsPP3:
        if g[dayString] == '6':
          numEarlyPP3 += 1
        elif g[dayString] == '6-C':
          numEarlyPP3 += 1
          numChargePP3 += 1
        elif g[dayString] == '7*':
          numBackupPP3 += 1
        elif g[dayString] == '7*-C':
          numBackupPP3 += 1
          numChargePP3 += 1
        elif g[dayString] == '8':
          numLatePP3 += 1
        elif g[dayString] == '8-C':
          numLatePP3 += 1
          numChargePP3 += 1
        elif g[dayString] == '7-C':
          numChargePP3 += 1
      numEarly = numEarlyPP1 + numEarlyPP2 + numEarlyPP3
      numBackup = numBackupPP1 + numBackupPP2 + numBackupPP3
      numLate = numLatePP1 + numLatePP2 + numLatePP3
      numCharge = numChargePP1 + numChargePP2 + numChargePP3
      #Update # 6/7*/8 Shifts and # 6/7*/8 Shifts PP1/2/3
      #early
      key = '# 6 Shifts;' + nurseName
      row = instanceStats[key]
      row['stat'] = numEarly
      target = row['stat_target']
      if numEarly <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #backup
      key = '# 7* Shifts;' + nurseName
      row = instanceStats[key]
      row['stat'] = numBackup
      target = row['stat_target']
      if numBackup <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #late
      key = '# 8 Shifts;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLate
      target = row['stat_target']
      if numLate <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #charge
      key = '# C Shifts;' + nurseName
      row = instanceStats[key]
      row['stat'] = numCharge
      target = row['stat_target']
      if numCharge <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #early pp1
      key = '# 6 Shifts PP1;' + nurseName
      row = instanceStats[key]
      row['stat'] = numEarlyPP1
      target = row['stat_target']
      if numEarlyPP1 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #early pp2
      key = '# 6 Shifts PP2;' + nurseName
      row = instanceStats[key]
      row['stat'] = numEarlyPP2
      target = row['stat_target']
      if numEarlyPP2 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #early pp3
      key = '# 6 Shifts PP3;' + nurseName
      row = instanceStats[key]
      row['stat'] = numEarlyPP3
      target = row['stat_target']
      if numEarlyPP3 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #backup pp1
      key = '# 7* Shifts PP1;' + nurseName
      row = instanceStats[key]
      row['stat'] = numBackupPP1
      target = row['stat_target']
      if numBackupPP1 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #backup pp2
      key = '# 7* Shifts PP2;' + nurseName
      row = instanceStats[key]
      row['stat'] = numBackupPP2
      target = row['stat_target']
      if numBackupPP2 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #backup pp3
      key = '# 7* Shifts PP3;' + nurseName
      row = instanceStats[key]
      row['stat'] = numBackupPP3
      target = row['stat_target']
      if numBackupPP3 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #late pp1
      key = '# 8 Shifts PP1;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLatePP1
      target = row['stat_target']
      if numLatePP1 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #late pp2
      key = '# 8 Shifts PP2;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLatePP2
      target = row['stat_target']
      if numLatePP2 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #late pp3
      key = '# 8 Shifts PP3;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLatePP3
      target = row['stat_target']
      if numLatePP3 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #charge pp1
      key = '# C Shifts PP1;' + nurseName
      row = instanceStats[key]
      row['stat'] = numChargePP1
      target = row['stat_target']
      if numChargePP1 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #charge pp2
      key = '# C Shifts PP2;' + nurseName
      row = instanceStats[key]
      row['stat'] = numChargePP2
      target = row['stat_target']
      if numChargePP2 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #charge pp3
      key = '# C Shifts PP3;' + nurseName
      row = instanceStats[key]
      row['stat'] = numChargePP3
      target = row['stat_target']
      if numChargePP3 <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Mon/Fri Worked
      numMFWorking = 0
      for dayString in dayStringsMondaysFridays:
        shift = g[dayString]
        if shift not in ('',None,'Off','PTO','H'):
          numMFWorking += 1
      #Update # Mon/Fri Worked
      key = '# Mon/Fri Worked;' + nurseName
      row = instanceStats[key]
      row['stat'] = numMFWorking
      target = row['stat_target']
      if numMFWorking <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Fri worked
      numFriWorking = 0
      for dayString in dayStringsFridays:
        shift = g[dayString]
        if shift not in ('',None,'Off','PTO','H'):
          numFriWorking += 1
      #Update # Fri Worked
      key = '# Fri Worked;' + nurseName
      row = instanceStats[key]
      row['stat'] = numFriWorking
      target = row['stat_target']
      if numFriWorking <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Late Fridays
      numLateFridaysWorked = 0
      for dayString in dayStringsFridays:
        shift = g[dayString]
        if shift in ('8','8-C'):
          numLateFridaysWorked += 1
      #Update # Late Fridays
      key = '# Late Fridays;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLateFridaysWorked
      target = row['stat_target']
      if numLateFridaysWorked <= target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Late Then Early
      numLateThenEarly = 0
      for i in range(len(dayStrings) - 1):
        dayString1 = dayStrings[i]
        dayString2 = dayStrings[i + 1]
        shift1 = g[dayString1]
        shift2 = g[dayString2]
        if dayString1 not in dayStringsFridays and shift1 in ('8','8-C') and shift2 in ('6','6-C'):
          numLateThenEarly += 1
      #Update # Late Then Early
      key = '# Late Then Early;' + nurseName
      row = instanceStats[key]
      row['stat'] = numLateThenEarly
      target = row['stat_target']
      if numLateThenEarly == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
      #Get stat for # Consecutive Lates
      numConsecutiveLates = 0
      for i in range(len(dayStrings) - 1):
        dayString1 = dayStrings[i]
        dayString2 = dayStrings[i + 1]
        shift1 = g[dayString1]
        shift2 = g[dayString2]
        if dayString1 not in dayStringsFridays and shift1 in ('8','8-C') and shift2 in ('8','8-C'):
          numConsecutiveLates += 1
      #Update # Consecutive Lates
      key = '# Consecutive Lates;' + nurseName
      row = instanceStats[key]
      row['stat'] = numConsecutiveLates
      target = row['stat_target']
      if numConsecutiveLates == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'  
      
  #Update the number of early shifts assigned to each day
  for key in instanceStats:
    if '# 6 Shifts (Per Day)' in key:
      row = instanceStats[key]
      dayString = row['day_string']
      numEarly = numEarlyDict[dayString]
      row['stat'] = numEarly
      target = row['stat_target']
      if numEarly == target:
        row['target_met_yn'] = 'Yes'
      else:
        row['target_met_yn'] = 'No'
  #Update the number of backup late assigned to each day
  for key in instanceStats:
    if '# 7* Shifts (Per Day)' in key:
      backupRow = instanceStats[key]
      dayString = backupRow['day_string']
      numBackup = numBackupDict[dayString]
      backupRow['stat'] = numBackup
      target = backupRow['stat_target']
      if numBackup == target:
        backupRow['target_met_yn'] = 'Yes'
      else:
        backupRow['target_met_yn'] = 'No'
  #Update the number of late shifts assigned to each day
  for key in instanceStats:
    if '# 8 Shifts (Per Day)' in key:
      lateRow = instanceStats[key]
      dayString = lateRow['day_string']
      numLate = numLateDict[dayString]
      lateRow['stat'] = numLate
      target = lateRow['stat_target']
      if numLate == target:
        lateRow['target_met_yn'] = 'Yes'
      else:
        lateRow['target_met_yn'] = 'No'
  #Update the number of charge shifts assigned to each day
  for key in instanceStats:
    if '# C Shifts (Per Day)' in key:
      chargeRow = instanceStats[key]
      dayString = chargeRow['day_string']
      numCharge = numChargeDict[dayString]
      chargeRow['stat'] = numCharge
      target = chargeRow['stat_target']
      if numCharge == target:
        chargeRow['target_met_yn'] = 'Yes'
      else:
        chargeRow['target_met_yn'] = 'No'
  instance['instance_stats'] = instanceStats

#This function is called after a new schedule instance is generated and before any edits are made to the instance
#It is intended solely to populate the instancestats table with empty stat data so that the structure of the table is there and ready to be updated/refreshed. It does however populate the stat target data which remains unchanged on refresh
@anvil.server.callable
def initialize_instance_stats(scheduleID,instanceID,nurses,earlyLate,backupLate,maxEarlyLate,maxBackupLate,availableFridays,maxCharge,chargeNurses,chargeDist,holidays,numDays,calendar):
  instanceStats = {}
  dayStrings = ['day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10','day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20','day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30']
  dayStringsPP1 = ['day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10']
  dayStringsPP2 = ['day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20']
  dayStringsPP3 = ['day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30']
  dayStringsMondaysFridays = ['day_1','day_2','day_6','day_7','day_11','day_12','day_16','day_17','day_21','day_22','day_26','day_27']
  dayStringsFridays = ['day_1','day_6','day_11','day_16','day_21','day_26']
  #Initialize stat types such that its granularity is based on date rather than nurse name
  for dayString in dayStrings:
    dateStr = daystring_to_datestring(scheduleID,dayString)
    dt = daystring_to_date(scheduleID,dayString)
    ci = get_calendar_index(dt,calendar,numDays)
    #Each day is assigned exactly two early nurses
    primaryKey = '# 6 Shifts (Per Day);' + dateStr
    statTarget = 2
    if ci in holidays:
      statTarget = 0
    instanceStats[primaryKey] = {'stat_type':'# 6 Shifts (Per Day)','nurse_or_day':dateStr,'day_string':dayString,'stat':2,'stat_target':statTarget,'target_met_yn':'Yes'}
    #Each day is assigned exactly two late nurses
    primaryKey = '# 8 Shifts (Per Day);' + dateStr
    statTarget = 2
    if ci in holidays:
      statTarget = 0
    instanceStats[primaryKey] = {'stat_type':'# 8 Shifts (Per Day)','nurse_or_day':dateStr,'day_string':dayString,'stat':2,'stat_target':statTarget,'target_met_yn':'Yes'}
    #Each day is assigned exactly one backup late nurse, or 0 in cases where demand for the day is 4 in which case a backup late person is not necessary
    dailyBackupLate = get_daily_backup_late(scheduleID,instanceID)
    primaryKey = '# 7* Shifts (Per Day);' + dateStr
    instanceStats[primaryKey] = {'stat_type':'# 7* Shifts (Per Day)','nurse_or_day':dateStr,'day_string':dayString,'stat':dailyBackupLate[dayString],'stat_target':dailyBackupLate[dayString],'target_met_yn':'Yes'}
    #Each day is assigned exactly one charge nurse
    statTarget = 1
    if ci in holidays:
      statTarget = 0
    primaryKey = '# C Shifts (Per Day);' + dateStr
    instanceStats[primaryKey] = {'stat_type':'# C Shifts (Per Day)','nurse_or_day':dateStr,'day_string':dayString,'stat':1,'stat_target':statTarget,'target_met_yn':'Yes'}
  for g in app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID, row_type = 'data'):
    fte = g['fte']
    nurseName = g['nurse_names']
    if fte not in ('OPT','ORIENT'): #nurse is FTE
      fte = float(fte)
      #FTE nurses work exactly their FTE each pay period
      primaryKey = '# Days Scheduled PP1;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Days Scheduled PP1','nurse_or_day':nurseName,'day_string':None,'stat':fte * 10,'stat_target':fte * 10,'target_met_yn':'Yes'}
      primaryKey = '# Days Scheduled PP2;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Days Scheduled PP2','nurse_or_day':nurseName,'day_string':None,'stat':fte * 10,'stat_target':fte * 10,'target_met_yn':'Yes'}
      primaryKey = '# Days Scheduled PP3;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Days Scheduled PP3','nurse_or_day':nurseName,'day_string':None,'stat':fte * 10,'stat_target':fte * 10,'target_met_yn':'Yes'}
      #FTE nurses work no more than their FTE each Mon-Fri workweek
      primaryKey = '# Workweeks Overloaded;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Workweeks Overloaded','nurse_or_day':nurseName,'day_string':None,'stat':0,'stat_target':0,'target_met_yn':'Yes'}
      #Nurses work a fair and balanced number of early/backup late/late/charge shifts
      nursesLength = len(nurses)
      foundNurseIndex = False
      k = 0
      while not foundNurseIndex and k < nursesLength:
        nm = nurses[k][0]
        if nurseName == nm:
          foundNurseIndex = True
        else:
          k += 1
      earlyLateTarget = earlyLate[k]
      backupLateTarget = backupLate[k]
      numChargeNurses = len(chargeNurses)
      foundChargeIndex = False
      index = 0
      while not foundChargeIndex and index < numChargeNurses:
        chargeIndex = chargeDist[index][0]
        if k == chargeIndex:
          foundChargeIndex = True
        else:
          index += 1
      if foundChargeIndex:
        chargeTarget = chargeDist[index][1]
        chargePPTarget = maxCharge[k]
      else: 
        chargeTarget = 0
        chargePPTarget = 0
      earlyLatePPTarget = maxEarlyLate[k]
      backupLatePPTarget = maxBackupLate[k]
      primaryKey = '# 6 Shifts;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 6 Shifts','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':math.ceil(earlyLateTarget),'target_met_yn':'Yes'}
      primaryKey = '# 7* Shifts;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 7* Shifts','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':math.ceil(backupLateTarget),'target_met_yn':'Yes'}
      primaryKey = '# 8 Shifts;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 8 Shifts','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':math.ceil(earlyLateTarget),'target_met_yn':'Yes'}
      primaryKey = '# C Shifts;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# C Shifts','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':math.ceil(chargeTarget),'target_met_yn':'Yes'}
      primaryKey = '# 6 Shifts PP1;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 6 Shifts PP1','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 6 Shifts PP2;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 6 Shifts PP2','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 6 Shifts PP3;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 6 Shifts PP3','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 7* Shifts PP1;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 7* Shifts PP1','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':backupLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 7* Shifts PP2;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 7* Shifts PP2','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':backupLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 7* Shifts PP3;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 7* Shifts PP3','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':backupLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 8 Shifts PP1;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 8 Shifts PP1','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 8 Shifts PP2;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 8 Shifts PP2','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# 8 Shifts PP3;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# 8 Shifts PP3','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':earlyLatePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# C Shifts PP1;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# C Shifts PP1','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':chargePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# C Shifts PP2;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# C Shifts PP2','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':chargePPTarget,'target_met_yn':'Yes'}
      primaryKey = '# C Shifts PP3;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# C Shifts PP3','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':chargePPTarget,'target_met_yn':'Yes'}
      #Each nurse is scheduled a fair number of Mondays and Fridays
      maxMF = get_max_mf_worked(fte)
      primaryKey = '# Mon/Fri Worked;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Mon/Fri Worked','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':maxMF,'target_met_yn':'Yes'}
      #Each nurse is scheduled a fair number of Fridays
      maxFri = get_max_fri_worked(fte)
      primaryKey = '# Fri Worked;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Fri Worked','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':maxFri,'target_met_yn':'Yes'}
      #Each nurse is scheduled a fair number of late Fridays
      maxLateFridays = availableFridays[k][2]
      primaryKey = '# Late Fridays;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Late Fridays','nurse_or_day':nurseName,'day_string':None,'stat':None,'stat_target':maxLateFridays,'target_met_yn':'Yes'}
      #A nurse cannot work late shift one day and then early shift the very next day
      primaryKey = '# Late Then Early;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Late Then Early','nurse_or_day':nurseName,'day_string':None,'stat':0,'stat_target':0,'target_met_yn':'Yes'}
      #A nurse cannot work two late shifts over two consecutive days
      primaryKey = '# Consecutive Lates;' + nurseName
      instanceStats[primaryKey] = {'stat_type':'# Consecutive Lates','nurse_or_day':nurseName,'day_string':None,'stat':0,'stat_target':0,'target_met_yn':'Yes'}
  instance = app_tables.instances.get(schedule_id = scheduleID, instance_id = instanceID)
  instance['instance_stats'] = instanceStats

@anvil.server.callable
def show_instance_stats(scheduleID,instanceID,typeFilter,nameFilter,targetFilter,sortString):
  instance = app_tables.instances.get(schedule_id = scheduleID, instance_id = instanceID)
  instanceStats = instance['instance_stats']
  #initialize filter lists
  if typeFilter in ('All',None):
    typeInclude = [
      '# 6 Shifts (Per Day)',
      '# 7* Shifts (Per Day)',
      '# 8 Shifts (Per Day)',
      '# C Shifts (Per Day)',
      '# Days Scheduled PP1',
      '# Days Scheduled PP2',
      '# Days Scheduled PP3',
      '# Workweeks Overloaded',
      '# 6 Shifts',
      '# 7* Shifts',
      '# 8 Shifts',
      '# C Shifts',
      '# 6 Shifts PP1',
      '# 6 Shifts PP2',
      '# 6 Shifts PP3',
      '# 7* Shifts PP1',
      '# 7* Shifts PP2',
      '# 7* Shifts PP3',
      '# 8 Shifts PP1',
      '# 8 Shifts PP2',
      '# 8 Shifts PP3',
      '# C Shifts PP1',
      '# C Shifts PP2',
      '# C Shifts PP3',
      '# Mon/Fri Worked',
      '# Fri Worked',
      '# Late Fridays',
      '# Late Then Early',
      '# Consecutive Lates'
    ]
  else:
    typeInclude = [typeFilter]
  if targetFilter in ('All',None):
    targetInclude = ['Yes','No']
  else:
    targetInclude = [targetFilter]
  #Put all the instanceStats dictionary rows into a list based on filtering
  filteredStats = [] #list of dictionaries
  for key in instanceStats:
    row = instanceStats[key]
    statType = row['stat_type']
    nurseOrDay = row['nurse_or_day']
    targetMetYN = row['target_met_yn']
    dayString = row['day_string']
    if dayString not in ('',None):
      date = daystring_to_date(scheduleID,dayString)
      row['date'] = date #include date for sorting
    else:
      row['date'] = datetime.now().date() - timedelta(days=1000) #dummy date that means nothing; it's useful only for sorting
    if statType in typeInclude and targetMetYN in targetInclude and (nameFilter in ('All',None) or (nameFilter not in ('All',None) and nurseOrDay == nameFilter)):
      filteredStats.append(row)
  #Return sorted instanceStats data
  if sortString == 'Type':
    filteredStats = sorted(filteredStats, key = lambda x: (x['stat_type'],x['date'],x['nurse_or_day']))
  elif sortString == 'Name':
    filteredStats = sorted(filteredStats, key = lambda x: (x['date'],x['nurse_or_day'],x['stat_type']))
  elif sortString == 'Hit Target':
    filteredStats = sorted(filteredStats, key = lambda x: (x['target_met_yn'],x['stat_type'],x['date'],x['nurse_or_day']))
  return filteredStats
  
@anvil.server.callable
def send_change_pw_email(user):
  emailAddress = user['email']
  anvil.users.send_password_reset_email(emailAddress)

def is_holiday(scheduleID, dateToCheck):
  isHoliday = False
  for r in app_tables.holidays.search(schedule_id = scheduleID):
    if r['holiday'] == dateToCheck:
      isHoliday = True
  return isHoliday

#fte parameter can be a decimal string, 'OPT', or 'ORIENT'
def get_fte_sortable(userID,fte):
  if fte == 'OPT':
    return 0
  elif fte == 'ORIENT':
    user = app_tables.users.get(user_id = userID)
    actualFte = user['fte']
    if actualFte == 'OPT':
      return 0
    else: #fte nurse
      return -1 * float(actualFte)
  else:
    return -1 * float(fte)

#####DELETE FROM TABLES#####

#Delete a row
@anvil.server.callable
def delete_row(row):
  row.delete()

#Delete a roster row
@anvil.server.callable
def delete_roster_row(row,scheduleID):
  row.delete()
  rosterData = show_roster(scheduleID)
  usersDataIDs = get_roster_user_ids(scheduleID)
  usersData = show_users_for_roster(usersDataIDs)
  return [rosterData, usersData]

#Delete a PAT row
@anvil.server.callable
def delete_pat_row(row,scheduleID,sortString):
  row.delete()
  return show_pat(scheduleID,sortString)

@anvil.server.callable
def delete_holiday_row(row,scheduleID):
  row.delete()
  return show_holidays(scheduleID)

@anvil.server.callable
def delete_pto_row(row,scheduleID,sortString):
  row.delete()
  return show_pto(scheduleID,sortString)

@anvil.server.callable
def delete_off_row(row,scheduleID,sortString):
  row.delete()
  return show_off(scheduleID,sortString)

@anvil.server.callable
def delete_shifts_row(row,scheduleID,sortString):
  row.delete()
  return show_shifts(scheduleID,sortString)

@anvil.server.callable
def delete_acls_row(row,scheduleID,sortString):
  row.delete()
  return show_acls(scheduleID,sortString)

@anvil.server.callable
def delete_opt_request(row,scheduleID,user):
  row.delete()
  return show_opt_user(scheduleID,user)

@anvil.server.callable
def delete_opt_row(row,scheduleID,sortString):
  row.delete()
  return show_opt(scheduleID,sortString)

#####UPDATE TABLES#####

#Accepts a row already tied to a table, a column, and the value to set for the data that lies at the intersection
#of the row and column
@anvil.server.callable
def update_table_value(nurseRow,colString,value):
  nurseRow[colString] = value

@anvil.server.callable
def update_user(row,colString,value):
  row[colString] = value

@anvil.server.callable
def update_user_and_roster(row,colString,value):
  #update user table
  update_user(row,colString,value)
  #update roster table
  userID = row['user_id']
  for sched in app_tables.schedules.search(status = q.none_of('',None,'Completed')):
    scheduleID = sched['schedule_id']
    r = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    if r != None:
      r[colString] = value

@anvil.server.callable
def update_user_and_roster_sd(row,value):
  #update user table
  row['start_date'] = value
  if value not in ('',None):
    row['start_date_str'] = datetime.strptime(str(value),'%Y-%m-%d').strftime('%b %d, %Y')
  else:
    row['start_date_str'] = value
  #update roster table
  userID = row['user_id']
  for sched in app_tables.schedules.search(status = q.none_of('',None,'Completed')):
    scheduleID = sched['schedule_id']
    r = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    if r != None:
      r['start_date'] = value
      if value not in ('',None):
        r['start_date_str'] = datetime.strptime(str(value),'%Y-%m-%d').strftime('%b %d, %Y')
      else:
        r['start_date_str'] = value

#update the status of a given schedule
@anvil.server.callable
def update_schedule_status(scheduleID,value):
  row = app_tables.schedules.get(schedule_id = scheduleID)
  row['status'] = value
  #Also update pto_email_sent_tf if the status just became 'Supervisor to complete PTO form'
  if value == 'Supervisor to complete PTO form':
    row.update(pto_email_sent_tf = True)

@anvil.server.callable
def update_cna(row,colString,value):
  row[colString] = value

#update a value in CNA table to reflect the CNA has PTO that day
def update_cna_with_pto(scheduleID,userID,dayString):
  r = app_tables.cna.get(schedule_id = scheduleID, user_id = userID)
  value = r[dayString]
  if value != 'H':
    r[dayString] = 'PTO'

@anvil.server.callable
def is_marked_complete(scheduleID):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  isRosterComplete = r['roster_complete_tf']
  isDemandComplete = r['demand_complete_tf']
  isCNAComplete = r['cna_complete_tf']
  isPATComplete = r['pat_complete_tf']
  isReviewComplete = r['review_complete_tf']
  return [isRosterComplete, isDemandComplete, isCNAComplete, isPATComplete, isReviewComplete]
  
#Mark a step as complete, and return whether each step is complete
@anvil.server.callable
def mark_complete(scheduleID,columnName):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  r[columnName] = True
  isCompleteList = is_marked_complete(scheduleID)
  return isCompleteList

@anvil.server.callable
def update_pto(row,scheduleID,name,ptoDate,sortString):
  #associate the name with the user id in the roster
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  row.update(
    user_id = userID,
    nurse_name = name,
    pto_date = ptoDate
  )
  return show_pto(scheduleID,sortString)

@anvil.server.callable
def update_off(row,scheduleID,name,offDate,sortString):
  #associate the name with the user id in the roster
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  row.update(
    user_id = userID,
    nurse_name = name,
    off_date = offDate
  )
  return show_off(scheduleID,sortString)

@anvil.server.callable
def update_shifts(row,scheduleID,name,shiftsDate,shift,sortString):
  #associate the name with the user id in the roster
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  row.update(
    user_id = userID,
    nurse_name = name,
    date = shiftsDate,
    shift = shift
  )
  return show_shifts(scheduleID,sortString)

@anvil.server.callable
def update_acls(row,scheduleID,name,aclsDate,sortString):
  #associate the name with the user id in the roster
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  row.update(
    user_id = userID,
    nurse_name = name,
    acls_date = aclsDate
  )
  return show_acls(scheduleID,sortString)

@anvil.server.callable
def update_opt(row,scheduleID,name,optDate,sortString):
  #associate the name with the user id in the roster
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  row.update(
    user_id = userID,
    nurse_name = name,
    opt_date = optDate
  )
  return show_opt(scheduleID,sortString)

@anvil.server.callable
def get_footer2(scheduleID,instanceID):
  return app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer2')

@anvil.server.callable
def update_schedule(row,dayString,value):
  row[dayString] = value

@anvil.server.callable
def update_footer3(scheduleID,instanceID,dayString,value,payPeriod):
  row = app_tables.generatedschedules.get(schedule_id = scheduleID,instance_id = instanceID,row_type = 'footer3')
  originalValue = int(row[dayString])
  newValue = int(value)
  #update the demand value the user changed
  row[dayString] = value
  #update the total for the pay period
  totalPP1Str = row['nurse_names_2']
  totalPP1 = int(totalPP1Str)
  totalPP2Str = row['nurse_names_3']
  totalPP2 = int(totalPP2Str)
  totalPP3Str = row['nurse_names_4']
  totalPP3 = int(totalPP3Str)
  delta = newValue - originalValue
  if payPeriod == 1:
    totalPP1 += delta
    totalPP1Str = str(totalPP1)
    row['nurse_names_2'] = totalPP1Str
  elif payPeriod == 2:
    totalPP2 += delta
    totalPP2Str = str(totalPP2)
    row['nurse_names_3'] = totalPP2Str
  elif payPeriod == 3:
    totalPP3 += delta
    totalPP3Str = str(totalPP3)
    row['nurse_names_4'] = totalPP3Str
  return [totalPP1Str, totalPP2Str, totalPP3Str]
  
@anvil.server.callable
def refresh_schedule(scheduleID,instanceID,row,dayString,value):
  #update schedule with the changed value
  update_schedule(row,dayString,value)
  
  #update footer supply
  footerRow = get_footer2(scheduleID,instanceID)
  currentNumWorking = int(footerRow[dayString])
  changedNumWorking = 0
  for row in app_tables.generatedschedules.search(schedule_id = scheduleID, instance_id = instanceID, row_type = 'data'):
    shift = row[dayString]
    if shift in ('6','7','7*','8','6-C','7-C','7*-C','8-C'):
      changedNumWorking += 1
  if changedNumWorking != currentNumWorking:
    delta = changedNumWorking - currentNumWorking
    value = str(changedNumWorking)
    if dayString in ('day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10'):
      totalValue = str(int(footerRow['nurse_names_2']) + delta)
      totalString = 'nurse_names_2'
    elif dayString in ('day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20'):
      totalValue = str(int(footerRow['nurse_names_3']) + delta)
      totalString = 'nurse_names_3'
    elif dayString in ('day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30'):
      totalValue = str(int(footerRow['nurse_names_4']) + delta)
      totalString = 'nurse_names_4'
    update_schedule(footerRow,dayString,value) #update the number of nurses working on the day
    update_schedule(footerRow,totalString,totalValue) #update the total number of nurses working that pay period
  return get_footer2(scheduleID,instanceID)

@anvil.server.callable
def update_personal_email(userRow,email):
  userRow.update(personal_email = email)

@anvil.server.callable
def update_demand(row,value):
  row.update(demand = value)

@anvil.server.callable
def update_message_read(messageRow,isRead):
  messageRow.update(marked_as_read_tf = isRead)

@anvil.server.callable
def update_instance_status(scheduleID,instanceID,status):
  r = app_tables.instances.get(schedule_id = scheduleID, instance_id = instanceID)
  r['shared_status'] = status

@anvil.server.callable
def update_fill(row,value):
  row['recipient_requested_tf'] = value

@anvil.server.callable
def update_swap(row,value):
  row['recipient_requested_tf'] = value
  
#####SHOW DATA GRIDS#####

#generic show function
@anvil.server.callable
def show_data_grid(scheduleID,table):
  return table.search(schedule_id = scheduleID)

#Populate schedules data grid
#hiddenList is intended to be either [False] or [True,False] or [False,True] which can be used to show all schedules to the scheduler and hide selected schedules from everyone else
@anvil.server.callable
def show_schedules(hiddenList):
  return app_tables.schedules.search(
    tables.order_by('schedule_start_date', ascending = False),
    tables.order_by('created_datetime', ascending = False),
    hidden_tf = q.any_of(*hiddenList)
  )

#populate users data grid
@anvil.server.callable
def show_users():
  return app_tables.users.search(
    tables.order_by('enabled',ascending=False),
    tables.order_by('created_datetime',ascending=False)
  )

#idsToExclude is a list [] of user_id's to exclude from the view
@anvil.server.callable
def show_users_for_roster(idsToExclude):
  return app_tables.users.search(
    tables.order_by('fte',ascending=False),
    tables.order_by('name'),
    enabled = True,
    fte = q.none_of('','None',None),
    user_id = q.none_of(*idsToExclude)
  )

#populate rosters data grid
@anvil.server.callable
def show_roster(scheduleID):
  return app_tables.roster.search(tables.order_by('added_datetime',ascending=False),schedule_id = scheduleID)

@anvil.server.callable
def show_opt_user(scheduleID,user):
  userID = user['user_id']
  return app_tables.opt.search(tables.order_by('opt_date'),schedule_id = scheduleID, user_id = userID)

@anvil.server.callable
def show_pat(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.pat.search(tables.order_by('nurse_name'),tables.order_by('pat_date'),schedule_id = scheduleID)
  elif sortString == 'date':
    return app_tables.pat.search(tables.order_by('pat_date'),tables.order_by('nurse_name'),schedule_id = scheduleID)

@anvil.server.callable
def show_holidays(scheduleID):
  return app_tables.holidays.search(tables.order_by('holiday'),schedule_id = scheduleID)

@anvil.server.callable
def show_pto(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.pto.search(tables.order_by('nurse_name'),tables.order_by('pto_date'),schedule_id = scheduleID,included_in_roster_tf = True)
  elif sortString == 'date':
    return app_tables.pto.search(tables.order_by('pto_date'),tables.order_by('nurse_name'),schedule_id = scheduleID,included_in_roster_tf = True)

@anvil.server.callable
def show_off(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.off.search(tables.order_by('nurse_name'),tables.order_by('off_date'),schedule_id = scheduleID,included_in_roster_tf = True)
  elif sortString == 'date':
    return app_tables.off.search(tables.order_by('off_date'),tables.order_by('nurse_name'),schedule_id = scheduleID,included_in_roster_tf = True)

@anvil.server.callable
def show_shifts(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.shiftsunavailable.search(tables.order_by('nurse_name'),tables.order_by('date'),schedule_id = scheduleID,included_in_roster_tf = True)
  elif sortString == 'date':
    return app_tables.shiftsunavailable.search(tables.order_by('date'),tables.order_by('nurse_name'),schedule_id = scheduleID,included_in_roster_tf = True)

@anvil.server.callable
def show_acls(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.acls.search(tables.order_by('nurse_name'),tables.order_by('acls_date'),schedule_id = scheduleID,included_in_roster_tf = True)
  elif sortString == 'date':
    return app_tables.acls.search(tables.order_by('acls_date'),tables.order_by('nurse_name'),schedule_id = scheduleID,included_in_roster_tf = True)

@anvil.server.callable
def show_opt(scheduleID,sortString):
  if sortString == 'name':
    return app_tables.opt.search(tables.order_by('nurse_name'),tables.order_by('opt_date'),schedule_id = scheduleID,included_in_roster_tf = True)
  elif sortString == 'date':
    return app_tables.opt.search(tables.order_by('opt_date'),tables.order_by('nurse_name'),schedule_id = scheduleID,included_in_roster_tf = True)

@anvil.server.callable
def show_instances(scheduleID):
  return app_tables.instances.search(tables.order_by('shared_status',ascending=False),tables.order_by('datetime_created',ascending=False),schedule_id = scheduleID)

#return schedule data
@anvil.server.callable
def get_schedule_in_pieces(scheduleID,instanceID,user,isCalledFromPublished):
  #get headers, data, and footers from the generated schedule
  header1 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'header1')
  header2 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'header2')
  footer1 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer1')
  footer2 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer2')
  footer3 = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer3')
  footer5 = app_tables.generatedschedules.search(schedule_id = scheduleID, instance_id = instanceID, row_type = 'footer5')
  data = app_tables.generatedschedules.search(schedule_id = scheduleID, instance_id = instanceID, row_type = 'data')
  data = sorted(data, key = lambda x: (x['fte_sortable'],x['nurse_names']))
  #get the schedule status
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  scheduleStatus = sched['status']
  #get any fills the user has requested
  userID = user['user_id']
  fillInfo = []
  if isCalledFromPublished:
    for fill in app_tables.fill.search(schedule_id = scheduleID, instance_id = instanceID, requester_user_id = userID, request_active_tf = True):
      fillDayString = fill['day_string']
      fillID = fill['fill_id']
      fillInfo.append([fillID,daystring_to_datestring(scheduleID,fillDayString)])
  #get any fills someone else has requested this user to fill
  fillRequestsReceived = []
  for recipient in app_tables.fillrecipients.search(schedule_id = scheduleID, instance_id = instanceID, recipient_user_id = userID, recipient_requested_tf = True, response = q.any_of(None,'')):
    fillID = recipient['fill_id']
    fill = app_tables.fill.get(fill_id = fillID)
    isActiveFill = fill['request_active_tf']
    if isActiveFill:
      requesterName = fill['requester_name']
      requestedDayString = fill['day_string']
      dateString = daystring_to_datestring(scheduleID,requestedDayString)
      fillRequestsReceived.append([requesterName,requestedDayString,dateString,fillID])
  #get any swaps the user has requested
  swapInfo = []
  if isCalledFromPublished:
    for swap in app_tables.swap.search(schedule_id = scheduleID, instance_id = instanceID, requester_user_id = userID, request_active_tf = True):
      requestedDayString = swap['requester_day_string']
      swapID = swap['swap_id']
      swapInfo.append([swapID,daystring_to_datestring(scheduleID,requestedDayString)])
  #get any swaps someone else has requested of this user
  swapRequestsReceived = []
  for recipient in app_tables.swaprecipients.search(schedule_id = scheduleID, instance_id = instanceID, recipient_user_id = userID, recipient_requested_tf = True, response = q.any_of(None,'')):
    swapID = recipient['swap_id']
    swap = app_tables.swap.get(swap_id = swapID)
    isActiveSwap = swap['request_active_tf']
    if isActiveSwap:
      requesterName = swap['requester_name']
      requestedDayString = swap['requester_day_string']
      requestedDateString = daystring_to_datestring(scheduleID,requestedDayString)
      requesterShift = swap['requester_shift']
      recipientDayString = recipient['recipient_day_string']
      recipientDateString = recipient['recipient_date_string']
      recipientShift = recipient['recipient_shift']
      swapRequestsReceived.append([swapID,requesterName,requestedDayString,requestedDateString,requesterShift,recipientDayString,recipientDateString,recipientShift])
  #refresh the instance stats table data and get its data to show
  if isCalledFromPublished:
    instanceStatsData = None
    namesList = None
    isNameFiltered = None
    nameFilter = None
  else: #handle instance stats stuff
    #get nurse names to populate the names filter items
    namesList = ['All']
    for r in app_tables.roster.search(schedule_id = scheduleID):
      namesList.append(r['nurse_name'])
    namesList.sort()
    isNameFiltered = False
    typeFilter = 'All'
    nameFilter = 'All'
    targetFilter = 'No'
    sortString = 'Type'
    update_instance_stats(scheduleID,instanceID)
    instanceStatsData = show_instance_stats(scheduleID,instanceID,typeFilter,nameFilter,targetFilter,sortString)
  return [header1,header2,data,footer2,footer3,footer5,fillInfo,fillRequestsReceived,swapInfo,swapRequestsReceived,scheduleStatus,instanceStatsData,namesList,footer1,isNameFiltered,nameFilter]

#returns the rows in the messages table as well as if any of those messages are unread
@anvil.server.callable
def get_messages(scheduleID,type,isUnreadOnly):
  isUnreadMessages = False
  if isUnreadOnly:
    messages = app_tables.messages.search(schedule_id = scheduleID, type = type, marked_as_read_tf = False)
    if len(messages) > 0:
      isUnreadMessages = True
    return [messages, isUnreadMessages]
  else:
    messages = app_tables.messages.search(tables.order_by('marked_as_read_tf',ascending=True), schedule_id = scheduleID, type = type)
    if len(messages) == 0:
      return [messages, False]
    topRow = messages[0]
    isTopRowRead = topRow['marked_as_read_tf']
    if not isTopRowRead:
      isUnreadMessages = True
    return [messages, isUnreadMessages]

#get the list of names of people who could fill in on a given day in a given schedule
@anvil.server.callable
def get_fill_recipients(scheduleID,instanceID,dayString):
  fillRecipients = {}
  for r in app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data'):
    recipientUserID = r['user_id']
    user = app_tables.users.get(user_id = recipientUserID)
    recipientEmail = user['email']
    if r[dayString] in (None,'','Off'):
      fillRecipients[recipientUserID] = [r['nurse_names'], recipientEmail]
  return fillRecipients

#####ADD ROWS TO TABLES#####

@anvil.server.callable
def add_schedule(scheduleID,scheduleStartDate):
  calendarDictionary = {
    'day_1': datetime.strptime(str(scheduleStartDate),'%Y-%m-%d').strftime('%b %d'),
    'day_2': datetime.strptime(str(scheduleStartDate + timedelta(days = 3)),'%Y-%m-%d').strftime('%b %d'),
    'day_3': datetime.strptime(str(scheduleStartDate + timedelta(days = 4)),'%Y-%m-%d').strftime('%b %d'),
    'day_4': datetime.strptime(str(scheduleStartDate + timedelta(days = 5)),'%Y-%m-%d').strftime('%b %d'),
    'day_5': datetime.strptime(str(scheduleStartDate + timedelta(days = 6)),'%Y-%m-%d').strftime('%b %d'),
    'day_6': datetime.strptime(str(scheduleStartDate + timedelta(days = 7)),'%Y-%m-%d').strftime('%b %d'),
    'day_7': datetime.strptime(str(scheduleStartDate + timedelta(days = 10)),'%Y-%m-%d').strftime('%b %d'),
    'day_8': datetime.strptime(str(scheduleStartDate + timedelta(days = 11)),'%Y-%m-%d').strftime('%b %d'),
    'day_9': datetime.strptime(str(scheduleStartDate + timedelta(days = 12)),'%Y-%m-%d').strftime('%b %d'),
    'day_10': datetime.strptime(str(scheduleStartDate + timedelta(days = 13)),'%Y-%m-%d').strftime('%b %d'),
    'day_11': datetime.strptime(str(scheduleStartDate + timedelta(days = 14)),'%Y-%m-%d').strftime('%b %d'),
    'day_12': datetime.strptime(str(scheduleStartDate + timedelta(days = 17)),'%Y-%m-%d').strftime('%b %d'),
    'day_13': datetime.strptime(str(scheduleStartDate + timedelta(days = 18)),'%Y-%m-%d').strftime('%b %d'),
    'day_14': datetime.strptime(str(scheduleStartDate + timedelta(days = 19)),'%Y-%m-%d').strftime('%b %d'),
    'day_15': datetime.strptime(str(scheduleStartDate + timedelta(days = 20)),'%Y-%m-%d').strftime('%b %d'),
    'day_16': datetime.strptime(str(scheduleStartDate + timedelta(days = 21)),'%Y-%m-%d').strftime('%b %d'),
    'day_17': datetime.strptime(str(scheduleStartDate + timedelta(days = 24)),'%Y-%m-%d').strftime('%b %d'),
    'day_18': datetime.strptime(str(scheduleStartDate + timedelta(days = 25)),'%Y-%m-%d').strftime('%b %d'),
    'day_19': datetime.strptime(str(scheduleStartDate + timedelta(days = 26)),'%Y-%m-%d').strftime('%b %d'),
    'day_20': datetime.strptime(str(scheduleStartDate + timedelta(days = 27)),'%Y-%m-%d').strftime('%b %d'),
    'day_21': datetime.strptime(str(scheduleStartDate + timedelta(days = 28)),'%Y-%m-%d').strftime('%b %d'),
    'day_22': datetime.strptime(str(scheduleStartDate + timedelta(days = 31)),'%Y-%m-%d').strftime('%b %d'),
    'day_23': datetime.strptime(str(scheduleStartDate + timedelta(days = 32)),'%Y-%m-%d').strftime('%b %d'),
    'day_24': datetime.strptime(str(scheduleStartDate + timedelta(days = 33)),'%Y-%m-%d').strftime('%b %d'),
    'day_25': datetime.strptime(str(scheduleStartDate + timedelta(days = 34)),'%Y-%m-%d').strftime('%b %d'),
    'day_26': datetime.strptime(str(scheduleStartDate + timedelta(days = 35)),'%Y-%m-%d').strftime('%b %d'),
    'day_27': datetime.strptime(str(scheduleStartDate + timedelta(days = 38)),'%Y-%m-%d').strftime('%b %d'),
    'day_28': datetime.strptime(str(scheduleStartDate + timedelta(days = 39)),'%Y-%m-%d').strftime('%b %d'),
    'day_29': datetime.strptime(str(scheduleStartDate + timedelta(days = 40)),'%Y-%m-%d').strftime('%b %d'),
    'day_30': datetime.strptime(str(scheduleStartDate + timedelta(days = 41)),'%Y-%m-%d').strftime('%b %d')
  }
  dttm = datetime.now(anvil.tz.tzoffset(hours=-5))
  scheduleEndDate = scheduleStartDate + timedelta(days = 41)
  app_tables.schedules.add_row(
    schedule_id = scheduleID,
    schedule = datetime.strptime(str(scheduleStartDate),'%Y-%m-%d').strftime('%b %d') + '-' + datetime.strptime(str(scheduleEndDate),'%Y-%m-%d').strftime('%b %d, %Y'),
    status = 'Scheduler to assemble roster',
    schedule_start_date = scheduleStartDate,
    hidden_tf = False,
    created_datetime = dttm,
    created_datetime_str = datetime.strptime(str(dttm),'%Y-%m-%d %H:%M:%S.%f-05:00').strftime('%b %d, %Y %I:%M %p'),
    pto_email_sent_tf = False,
    daystring_to_datestring = calendarDictionary,
    check_submitted = None,
    requests_submitted = 0,
    requests_needed = 0,
    roster_complete_tf = False,
    demand_complete_tf = False,
    cna_complete_tf = False,
    pat_complete_tf = False,
    review_complete_tf = False
  )

def get_new_user_id():
  biggestUserID = None
  for row in app_tables.users.search(tables.order_by('user_id',ascending = False)):
    biggestUserID = row['user_id']
    break
  if biggestUserID == None:
    return 1
  else:
    return biggestUserID + 1

#Also return users data for performant refresh
@anvil.server.callable
def add_user(name,email,title,startDate,isSupervisor,isScheduler,isCharge,isEnabled):
  userID = get_new_user_id()
  startDateStr = None
  if startDate not in ('',None):
    startDateStr = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
  app_tables.users.add_row(
    user_id = userID,
    name = name,
    email = email,
    fte = title,
    start_date = startDate,
    start_date_str = startDateStr,
    supervisor_tf = isSupervisor,
    scheduler_tf = isScheduler,
    charge_tf = isCharge,
    enabled = isEnabled,
    created_datetime = datetime.now()
  )
  return show_users()

#initialize the roster for the current schedule with the roster users from the previous schedule (match on the user IDs from the previous roster to know who's in, but take the data from the users table to make sure the data is up to date)
@anvil.server.callable
def load_roster(scheduleID):
  recentID = scheduleID - 1
  if recentID > 0:
    for r in app_tables.roster.search(schedule_id = recentID):
      userID = r['user_id']
      user = app_tables.users.get(user_id = userID)
      nurseName = user['name']
      nurseEmail = user['email']
      fte = user['fte']
      startDate = user['start_date']
      isCharge = user['charge_tf']
      startDateStr = None
      if startDate not in ('',None):
        startDateStr = datetime.strptime(str(startDate),'%Y-%m-%d').strftime('%b %d, %Y')
      app_tables.roster.add_row(
        schedule_id = scheduleID,
        user_id = userID,
        nurse_name = nurseName,
        nurse_email = nurseEmail,
        fte = fte,
        start_date = startDate,
        start_date_str = startDateStr,
        charge_tf = isCharge,
        added_datetime = datetime.now()
      )

#add the chosen holiday and return the holidays table for performant refresh
@anvil.server.callable
def add_holiday(scheduleID,holidayDate):
  #check if the addition will be a duplicate
  holidayList = [holidayDate]
  for h in app_tables.holidays.search(schedule_id = scheduleID):
    holidayList.append(h['holiday'])
  info = is_duplicates(holidayList)
  isDuplicates = info[0]
  if not isDuplicates:
    #add to holiday table
    app_tables.holidays.add_row(
      schedule_id = scheduleID,
      holiday = holidayDate,
      holiday_display = datetime.strptime(str(holidayDate),'%Y-%m-%d').strftime('%b %d, %Y')
    )
  return [isDuplicates, show_holidays(scheduleID)]

#only called when the scheduler is entering pto in scheduler input form
@anvil.server.callable
def add_pto(scheduleID,nurseName,ptoDate,sortString):
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, nurse_name = nurseName)
  userID = rosterRow['user_id']
  isDuplicate = False
  r = app_tables.pto.get(schedule_id = scheduleID, user_id = userID, pto_date = ptoDate)
  if r != None: #If there's already a row in pto for that person having pto on that date...
    isDuplicate = True
  if not isDuplicate:
    app_tables.pto.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      pto_date = ptoDate,
      pto_date_display = datetime.strptime(str(ptoDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      included_in_roster_tf = True
    )
  ptoData = show_pto(scheduleID,sortString)
  return [isDuplicate,ptoData]

#only called when the scheduler is entering requested off days in scheduler input form
@anvil.server.callable
def add_off(scheduleID,nurseName,offDate,sortString):
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, nurse_name = nurseName)
  userID = rosterRow['user_id']
  isHoliday = is_holiday(scheduleID,offDate)
  isDuplicate = False
  r = app_tables.off.get(schedule_id = scheduleID, user_id = userID, off_date = offDate)
  if r != None: #If there's already a row in off for that person requesting off that date...
    isDuplicate = True
  if not isDuplicate and not isHoliday:
    app_tables.off.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      off_date = offDate,
      off_date_display = datetime.strptime(str(offDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      included_in_roster_tf = True
    )
  offData = show_off(scheduleID,sortString)
  return [isDuplicate,isHoliday,offData]

#only called when the scheduler is entering shifts unavailable in scheduler input form
@anvil.server.callable
def add_shifts(scheduleID,nurseName,shiftsDate,shift,sortString):
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, nurse_name = nurseName)
  userID = rosterRow['user_id']
  isHoliday = is_holiday(scheduleID,shiftsDate)
  isDuplicate = False
  r = app_tables.shiftsunavailable.get(schedule_id = scheduleID, user_id = userID, date = shiftsDate, shift = shift)
  if r != None: #If there's already a row in shiftsunavailable for that person having requesting off a shift on that date...
    isDuplicate = True
  isFourthShift = False #This will be marked as true if there are already 3 of the 4 shifts (6, 7, 7*, 8) selected for this person on this date, meaning this would be the fourth shift selected for the day which is not allowed.
  if not isDuplicate and not isHoliday:
    r = app_tables.shiftsunavailable.search(schedule_id = scheduleID, user_id = userID, date = shiftsDate)
    if len(r) >= 3:
      isFourthShift = True
    if not isFourthShift:
      app_tables.shiftsunavailable.add_row(
        schedule_id = scheduleID,
        user_id = userID,
        nurse_name = nurseName,
        date = shiftsDate,
        date_display = datetime.strptime(str(shiftsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
        shift = shift,
        included_in_roster_tf = True
      )
  shiftsData = show_shifts(scheduleID,sortString)
  return [isDuplicate,isHoliday,isFourthShift,shiftsData]

#only called when the scheduler is entering ACLS in scheduler input form
@anvil.server.callable
def add_acls(scheduleID,nurseName,aclsDate,sortString):
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, nurse_name = nurseName)
  userID = rosterRow['user_id']
  isHoliday = is_holiday(scheduleID,aclsDate)
  isDuplicate = False
  r = app_tables.acls.get(schedule_id = scheduleID, user_id = userID, acls_date = aclsDate)
  if r != None: #If there's already a row in acls for that person having acls on that date...
    isDuplicate = True
  if not isDuplicate and not isHoliday:
    app_tables.acls.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      acls_date = aclsDate,
      acls_date_display = datetime.strptime(str(aclsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      included_in_roster_tf = True
    )
  aclsData = show_acls(scheduleID,sortString)
  return [isDuplicate,isHoliday,aclsData]

#only called when the scheduler is entering OPT in scheduler input form
@anvil.server.callable
def add_opt(scheduleID,nurseName,optDate,sortString):
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, nurse_name = nurseName)
  userID = rosterRow['user_id']
  isHoliday = is_holiday(scheduleID,optDate)
  isDuplicate = False
  r = app_tables.opt.get(schedule_id = scheduleID, user_id = userID, opt_date = optDate)
  if r != None: #If there's already a row in opt for that opt person working on that date...
    isDuplicate = True
  if not isDuplicate and not isHoliday:
    app_tables.opt.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      opt_date = optDate,
      opt_date_display = datetime.strptime(str(optDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      included_in_roster_tf = True
    )
  optData = show_opt(scheduleID,sortString)
  return [isDuplicate,isHoliday,optData]

#add to pto table
def load_pto(scheduleID):
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = sched['request_data']
  for userIDStr in requestData:
    userID = int(userIDStr)
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
    nurseName = rosterRow['nurse_name']
    fte = rosterRow['fte']
    personData = requestData[userIDStr]
    success = False
    personDataLength = len(personData)
    index = 0
    while not success and index < personDataLength:
      dataRow = personData[index]
      type = dataRow['row_type']
      if type == 'PTO':
        success = True
      else:
        index += 1
    for day in dataRow:
      if 'day_' in day and dataRow[day] == 'True' and 'FTE' in fte:
        ptoDate = daystring_to_date(scheduleID,day)
        app_tables.pto.add_row(
          schedule_id = scheduleID,
          user_id = userID,
          nurse_name = nurseName,
          pto_date = ptoDate,
          pto_date_display = datetime.strptime(str(ptoDate),'%Y-%m-%d').strftime('%b %d, %Y'),
          included_in_roster_tf = True
        )
      elif 'day_' in day and dataRow[day] == 'True' and fte == 'CNA':
        update_cna_with_pto(scheduleID,userID,day)

@anvil.server.callable
def add_message(scheduleID,user,senderName,type,text):
  userID = user['user_id']
  app_tables.messages.add_row(
    schedule_id = scheduleID,
    user_id = userID,
    sender_name = senderName,
    type = type,
    text = text,
    marked_as_read_tf = False,
    created_datetime_utc = datetime.today()
  )
  
#Add row to cna table with empty data
@anvil.server.callable
def add_cna(scheduleID,userID,name):
  app_tables.cna.add_row(
    schedule_id = scheduleID,
    user_id = userID,
    nurse_name = name,
    included_in_roster_tf = True,
    day_1 = '',
    day_2 = '',
    day_3 = '',
    day_4 = '',
    day_5 = '',
    day_6 = '',
    day_7 = '',
    day_8 = '',
    day_9 = '',
    day_10 = '',
    day_11 = '',
    day_12 = '',
    day_13 = '',
    day_14 = '',
    day_15 = '',
    day_16 = '',
    day_17 = '',
    day_18 = '',
    day_19 = '',
    day_20 = '',
    day_21 = '',
    day_22 = '',
    day_23 = '',
    day_24 = '',
    day_25 = '',
    day_26 = '',
    day_27 = '',
    day_28 = '',
    day_29 = '',
    day_30 = ''
  )

#Add rows to the CNA table for the given schedule ID. 
#If the CNA was active in the previous schedule, then load in their data from the previous schedule
#otherwise if the CNA is new to this schedule, add a row with email and name but with otherwise empty data
def load_cna(scheduleID):
  #add rows with empty data to the cna table for every active cna user
  for rosterRow in app_tables.roster.search(schedule_id = scheduleID, fte = 'CNA'):
    userID = rosterRow['user_id']
    name = rosterRow['nurse_name']
    recentCNA = app_tables.cna.search(schedule_id = scheduleID - 1)
    recentCNALength = len(recentCNA)
    if recentCNALength == 0:
      add_cna(scheduleID,userID,name)
    else:
      cnaDataAlreadyExists = False
      counter = 0
      while not cnaDataAlreadyExists and counter < recentCNALength:
        recentRow = recentCNA[counter]
        recentUserID = recentRow['user_id']
        if userID == recentUserID:
          cnaDataAlreadyExists = True
        else:
          counter += 1
      if not cnaDataAlreadyExists:
        add_cna(scheduleID,userID,name)
      else:
        defaultValue = None
        dayStrings = ['day_1','day_2','day_3','day_4','day_5','day_6','day_7','day_8','day_9','day_10','day_11','day_12','day_13','day_14','day_15','day_16','day_17','day_18','day_19','day_20','day_21','day_22','day_23','day_24','day_25','day_26','day_27','day_28','day_29','day_30']
        index = 0
        while defaultValue == None and index < 30:
          dayString = dayStrings[index]
          value = recentRow[dayString]
          if value not in ('',None,'PTO','H'):
            defaultValue = value
          else:
            index += 1
        d1 = recentRow['day_1']
        if d1 in ('PTO','H'):
          d1 = defaultValue
        d2 = recentRow['day_2']
        if d2 in ('PTO','H'):
          d2 = defaultValue
        d3 = recentRow['day_3']
        if d3 in ('PTO','H'):
          d3 = defaultValue
        d4 = recentRow['day_4']
        if d4 in ('PTO','H'):
          d4 = defaultValue
        d5 = recentRow['day_5']
        if d5 in ('PTO','H'):
          d5 = defaultValue
        d6 = recentRow['day_6']
        if d6 in ('PTO','H'):
          d6 = defaultValue
        d7 = recentRow['day_7']
        if d7 in ('PTO','H'):
          d7 = defaultValue
        d8 = recentRow['day_8']
        if d8 in ('PTO','H'):
          d8 = defaultValue
        d9 = recentRow['day_9']
        if d9 in ('PTO','H'):
          d9 = defaultValue
        d10 = recentRow['day_10']
        if d10 in ('PTO','H'):
          d10 = defaultValue
        d11 = recentRow['day_11']
        if d11 in ('PTO','H'):
          d11 = defaultValue
        d12 = recentRow['day_12']
        if d12 in ('PTO','H'):
          d12 = defaultValue
        d13 = recentRow['day_13']
        if d13 in ('PTO','H'):
          d13 = defaultValue
        d14 = recentRow['day_14']
        if d14 in ('PTO','H'):
          d14 = defaultValue
        d15 = recentRow['day_15']
        if d15 in ('PTO','H'):
          d15 = defaultValue
        d16 = recentRow['day_16']
        if d16 in ('PTO','H'):
          d16 = defaultValue
        d17 = recentRow['day_17']
        if d17 in ('PTO','H'):
          d17 = defaultValue
        d18 = recentRow['day_18']
        if d18 in ('PTO','H'):
          d18 = defaultValue
        d19 = recentRow['day_19']
        if d19 in ('PTO','H'):
          d19 = defaultValue
        d20 = recentRow['day_20']
        if d20 in ('PTO','H'):
          d20 = defaultValue
        d21 = recentRow['day_21']
        if d21 in ('PTO','H'):
          d21 = defaultValue
        d22 = recentRow['day_22']
        if d22 in ('PTO','H'):
          d22 = defaultValue
        d23 = recentRow['day_23']
        if d23 in ('PTO','H'):
          d23 = defaultValue
        d24 = recentRow['day_24']
        if d24 in ('PTO','H'):
          d24 = defaultValue
        d25 = recentRow['day_25']
        if d25 in ('PTO','H'):
          d25 = defaultValue
        d26 = recentRow['day_26']
        if d26 in ('PTO','H'):
          d26 = defaultValue
        d27 = recentRow['day_27']
        if d27 in ('PTO','H'):
          d27 = defaultValue
        d28 = recentRow['day_28']
        if d28 in ('PTO','H'):
          d28 = defaultValue
        d29 = recentRow['day_29']
        if d29 in ('PTO','H'):
          d29 = defaultValue
        d30 = recentRow['day_30']
        if d30 in ('PTO','H'):
          d30 = defaultValue
        app_tables.cna.add_row(
          schedule_id = scheduleID,
          user_id = userID,
          nurse_name = name,
          included_in_roster_tf = True,
          day_1 = d1,
          day_2 = d2,
          day_3 = d3,
          day_4 = d4,
          day_5 = d5,
          day_6 = d6,
          day_7 = d7,
          day_8 = d8,
          day_9 = d9,
          day_10 = d10,
          day_11 = d11,
          day_12 = d12,
          day_13 = d13,
          day_14 = d14,
          day_15 = d15,
          day_16 = d16,
          day_17 = d17,
          day_18 = d18,
          day_19 = d19,
          day_20 = d20,
          day_21 = d21,
          day_22 = d22,
          day_23 = d23,
          day_24 = d24,
          day_25 = d25,
          day_26 = d26,
          day_27 = d27,
          day_28 = d28,
          day_29 = d29,
          day_30 = d30
        ) 

#returns true/false for whether someone is working/pto etc. on a given day in a given schedule
def is_occupied_daystring(scheduleID,instanceID,userID,dayString):
  r = app_tables.generatedschedules.get(schedule_id = scheduleID, instance_id = instanceID, row_type = 'data', user_id = userID)
  if r == None:
    return False
  else:
    shift = r[dayString]
    if shift in (None,'','Off'):
      return False
  return True

@anvil.server.callable
def load_swaprecipients(swapID,recipientDate):
  swap = app_tables.swap.get(swap_id = swapID)
  scheduleID = swap['schedule_id']
  isSameDaySwap = False
  isOccupied = False
  requesterID = swap['requester_user_id']
  requesterDayString = swap['requester_day_string']
  recipientDayString = date_to_daystring(scheduleID,recipientDate)
  if recipientDayString == requesterDayString:
    isSameDaySwap = True
  if not isSameDaySwap: #the desired date must be different than the requester date
    instanceID = swap['instance_id']
    isOccupied = is_occupied_daystring(scheduleID,instanceID,requesterID,recipientDayString) #isOccupied is true if requester is occupied on the day he/she is trying to swap to
    if not isOccupied:
      user = app_tables.users.get(user_id = requesterID)
      isRequesterCharge = user['charge_tf']
      requesterShift = swap['requester_shift']
      #add a recipient to swaprecipients if it would be a valid swap: (1) the recipient must be occupied on the recipient day with a shift not equal to acls, pto, or off, (2) the recipient must not be occupied on the requester day, (3) the requester and recipient must both be qualified to work the shift (i.e. a non-charge nurse cannot work a charge shift)
      for r in app_tables.generatedschedules.search(schedule_id = scheduleID,instance_id = instanceID,row_type = 'data'):
        userID = r['user_id']
        if userID != requesterID:
          recipientID = userID
          recipient = app_tables.users.get(user_id = recipientID)
          isRecipientCharge = recipient['charge_tf']
          recipientShiftOnRecipientDay = r[recipientDayString]
          recipientShiftOnRequesterDay = r[requesterDayString]
          if recipientShiftOnRecipientDay not in (None,'','Off','ACLS','PTO','H') and recipientShiftOnRequesterDay in (None,'','Off') and ('-C' not in recipientShiftOnRecipientDay or ('-C' in recipientShiftOnRecipientDay and isRequesterCharge)) and ('-C' not in requesterShift or ('-C' in requesterShift and isRecipientCharge)): #the swap must be valid/not cause issues such as a non-charge nurse working a charge shift
            recipientName = recipient['name']
            recipientEmail = recipient['email']
            app_tables.swaprecipients.add_row(
              swap_id = swapID,
              schedule_id = scheduleID,
              instance_id = instanceID,
              recipient_user_id = recipientID,
              recipient_name = recipientName,
              recipient_email = recipientEmail,
              recipient_day_string = recipientDayString,
              recipient_date_string = datetime.strptime(str(recipientDate),'%Y-%m-%d').strftime('%b %d'),
              recipient_shift = recipientShiftOnRecipientDay,
              recipient_requested_tf = True
            )
  swapRecipientsData = app_tables.swaprecipients.search(swap_id = swapID, recipient_requested_tf = True)
  return [swapRecipientsData,isSameDaySwap,isOccupied]
        

@anvil.server.callable
def add_pat(scheduleID,name,patDate,sortString):
  #identify the user ID associated with the name which you've gone to great lengths to ensure that within a given schedule in the roster, the names are unique, so you can safely associate one name with one user ID
  r = app_tables.roster.get(schedule_id = scheduleID, nurse_name = name)
  userID = r['user_id']
  isHoliday = is_holiday(scheduleID,patDate)
  isDuplicate = False
  r = app_tables.pat.get(schedule_id = scheduleID, user_id = userID, pat_date = patDate)
  if r != None: #If there's already a row in pat for that person doing pat on that date...
    isDuplicate = True
  if not isDuplicate and not isHoliday:
    app_tables.pat.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = name,
      pat_date = patDate,
      pat_date_display = datetime.strptime(str(patDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      added_datetime = datetime.now(),
      included_in_roster_tf = True
    )
  patData = show_pat(scheduleID,sortString)
  return [isDuplicate,isHoliday,patData]

@anvil.server.callable
def add_opt_request(scheduleID,user,optDate):
  userID = user['user_id']
  nurseName = user['name']
  nurseEmail = user['email']
  #check if the opt date selection is a duplicate day to work or if it's the same day as a holiday
  isDuplicate = False
  for r in app_tables.opt.search(schedule_id = scheduleID, user_id = userID):
    if r['opt_date'] == optDate:
      isDuplicate = True
  isHoliday = is_holiday(scheduleID,optDate)
  if not isDuplicate and not isHoliday:
    app_tables.opt.add_row(
      schedule_id = scheduleID,
      user_id = userID,
      nurse_name = nurseName,
      nurse_email = nurseEmail,
      opt_date = optDate,
      opt_date_display = datetime.strptime(str(optDate),'%Y-%m-%d').strftime('%b %d, %Y'),
      included_in_roster_tf = True
    )
  optData = show_opt_user(scheduleID,user)
  return [isDuplicate,isHoliday,optData]

#This is intended to be called when the scheduler just created a new instance with a successful run of "Generate Schedule"
@anvil.server.callable
def add_instance(scheduleID,instanceID,instanceName):
  dttmCreated = datetime.now(anvil.tz.tzoffset(hours=-5))
  dttmCreatedStr = datetime.strptime(str(dttmCreated),'%Y-%m-%d %H:%M:%S.%f-05:00').strftime('%b %d, %Y %I:%M %p')
  app_tables.instances.add_row(
    schedule_id = scheduleID,
    instance_id = instanceID,
    instance_name = instanceName,
    shared_status = 'Not published',
    datetime_created = dttmCreated,
    datetime_created_str = dttmCreatedStr
  )

def get_new_fill_id():
  biggestFillID = None
  for row in app_tables.fill.search(tables.order_by('fill_id',ascending = False)):
    biggestFillID = row['fill_id']
    break
  if biggestFillID == None:
    return 1
  else:
    return biggestFillID + 1

@anvil.server.callable
def initialize_fill(scheduleID,instanceID,user,dayString):
  fillID = get_new_fill_id()
  requesterUserID = user['user_id']
  requesterName = user['name']
  requesterEmail = user['email']
  fillRecipients = get_fill_recipients(scheduleID,instanceID,dayString)
  app_tables.fill.add_row(
    fill_id = fillID,
    schedule_id = scheduleID,
    instance_id = instanceID,
    requester_user_id = requesterUserID,
    requester_name = requesterName,
    requester_email = requesterEmail,
    day_string = dayString,
    request_active_tf = False #It's false until the user submits the fill request
  )
  for recipientID in fillRecipients:
    recipientInfo = fillRecipients[recipientID]
    recipientName = recipientInfo[0]
    recipientEmail = recipientInfo[1]
    app_tables.fillrecipients.add_row(
      fill_id = fillID,
      schedule_id = scheduleID,
      instance_id = instanceID,
      recipient_user_id = recipientID,
      recipient_name = recipientName,
      recipient_email = recipientEmail,
      recipient_requested_tf = True
    )
  fillData = app_tables.fillrecipients.search(fill_id = fillID)
  return [fillID, fillData]

@anvil.server.callable
def initialize_fill_or_swap(scheduleID,instanceID,user,dayString):
  dateAdded = daystring_to_date(scheduleID,dayString)
  requesterID = user['user_id']
  fillInfo = is_active_fill(scheduleID,instanceID,requesterID,dayString)
  isActiveFill = fillInfo[0]
  fillID = fillInfo[1]
  swapInfo = is_active_swap(scheduleID,instanceID,requesterID,dayString)
  isActiveSwap = swapInfo[0]
  swapID = swapInfo[1]
  return [dateAdded, isActiveFill, isActiveSwap, fillID, swapID]

def get_new_swap_id():
  biggestSwapID = None
  for row in app_tables.swap.search(tables.order_by('swap_id',ascending = False)):
    biggestSwapID = row['swap_id']
    break
  if biggestSwapID == None:
    return 1
  else:
    return biggestSwapID + 1

@anvil.server.callable
def initialize_swap(scheduleID,instanceID,user,dayString,shift):
  swapID = get_new_swap_id()
  requesterUserID = user['user_id']
  requesterName = user['name']
  requesterEmail = user['email']
  app_tables.swap.add_row(
    swap_id = swapID,
    schedule_id = scheduleID,
    instance_id = instanceID,
    requester_user_id = requesterUserID,
    requester_name = requesterName,
    requester_email = requesterEmail,
    requester_day_string = dayString,
    requester_shift = shift,
    request_active_tf = False #It's false until the user submits the swap request
  )
  dateDisplay = daystring_to_datestring(scheduleID,dayString)
  return [swapID, dateDisplay]

#####EMAIL FUNCTIONS#####
  
#Note: if the user is both a supervisor and a scheduler, they will only be added to the supervisor list
def get_supervisors_and_schedulers():
  supervisorList = []
  schedulerList = []
  for row in app_tables.users.search(
    q.any_of(scheduler_tf = True, supervisor_tf = True),
    enabled = True #can log in
  ):
    if row['supervisor_tf']:
      supervisorList.append(row['email'])
    elif row['scheduler_tf']:
      schedulerList.append(row['email'])
  return [supervisorList, schedulerList]
  
#send the email to the supervisor to tell them it's time to enter pto and holidays
def send_pto_email():
  supervisorsAndSchedulers = get_supervisors_and_schedulers()
  toAddressList = supervisorsAndSchedulers[0] #supervisors list
  ccList = supervisorsAndSchedulers[1] #schedulers list
  for user in app_tables.users.search(email = q.any_of(*toAddressList)):
    personalEmail = user['personal_email']
    if personalEmail not in ('',None):
      toAddressList.append(user['personal_email'])
  anvil.email.send(
    from_name = 'Tachy',
    to = toAddressList,
    cc = ccList,
    subject = "[Schedule] Time to configure holidays & PTO!",
    text = 'Hey!' + '\n \n' + 'It\'s that time again. Log in to fill out the PTO & holiday forms.',
    html = 'Hey!' + '\n \n' + 'It\'s that time again. <a href="https://fsc.tachy.app">Log in</a> to fill out the PTO & holiday forms.'
  )

#send email alerting scheduler that a new request has been submitted
@anvil.server.callable
def send_request_email(scheduleID,user,numRequestsSubmitted,numRequestsNeeded):
  fte = user['fte']
  supervisorsAndSchedulers = get_supervisors_and_schedulers()
  toList = supervisorsAndSchedulers[1] #schedulers list
  for schedulerUser in app_tables.users.search(email = q.any_of(*toList)):
    personalEmail = schedulerUser['personal_email']
    if personalEmail not in ('',None):
      toList.append(personalEmail)
  ccAddress = user['email']
  ccName = user['name']
  userID = user['user_id']
  summaryString = """Request summary: \n"""
  if fte != 'OPT':
    userIDStr = str(userID)
    requestSummaryData = get_request_data_by_person(scheduleID,userIDStr)
    dayDictionary = get_calendar_dictionary(scheduleID)
    for day in requestSummaryData:
      if len(requestSummaryData[day]) > 0:
        summaryString += dayDictionary[day] + ': '
        index = 0
        for type in requestSummaryData[day]:
          if index == 0:
            summaryString += type
          else:
            summaryString += ', ' + type
          index += 1
        summaryString += '\n'
  else:
    index = 0
    for req in app_tables.opt.search(tables.order_by('opt_date'),schedule_id = scheduleID,user_id = userID):
      if index == 0:
        summaryString += req['opt_date_display']
      else:
        summaryString += ' | ' + req['opt_date_display']
      index += 1
    summaryString += '\n'
  for note in app_tables.messages.search(schedule_id = scheduleID,user_id = userID):
    noteText = note['text']
    summaryString += '\n' + noteText + '\n'
  anvil.email.send(
    from_name = 'Tachy',
    to = toList,
    cc = ccAddress,
    subject = '[Schedule] Request form submitted',
    text = 'Hey!' + '\n \n' + ccName + ' submitted their requests. \n \n' + summaryString 
  )
  if numRequestsSubmitted == numRequestsNeeded:
    anvil.email.send(
      from_name = 'Tachy',
      to = toList,
      subject = '[Schedule] Time to create the schedule!',
      text = 'Hey!' + '\n \n' + 'Everyone submitted their requests. Log in to create the schedule.',
      html = 'Hey!' + '\n \n' + 'Everyone submitted their requests. <a href="https://fsc.tachy.app">Log in</a> to create the schedule.'
    )

#####REQUEST DATA#####
#send an email to every active/enabled/FTE/OPT nurse to tell them it's time to submit their requests
#set the submitted requests column in schedules
@anvil.server.callable
def invite_nurse_requests(scheduleID):
  #update holidays data in schedules table. Also update CNA table with holidays
  holidayInit = {'day_1': 'False','day_2': 'False','day_3': 'False','day_4': 'False','day_5': 'False','day_6': 'False','day_7': 'False','day_8': 'False','day_9': 'False','day_10': 'False',
                 'day_11': 'False','day_12': 'False','day_13': 'False','day_14': 'False','day_15': 'False','day_16': 'False','day_17': 'False','day_18': 'False','day_19': 'False','day_20': 'False',
                 'day_21': 'False','day_22': 'False','day_23': 'False','day_24': 'False','day_25': 'False','day_26': 'False','day_27': 'False','day_28': 'False','day_29': 'False','day_30': 'False'
                }
  for h in app_tables.holidays.search(schedule_id = scheduleID):
    holidayDate = h['holiday']
    dayString = date_to_daystring(scheduleID,holidayDate)
    holidayInit[dayString] = 'True'
    #update CNA table with holidays
    for c in app_tables.cna.search(schedule_id = scheduleID):
      c[dayString] = 'H'
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  sched['holiday_data'] = {
    'row_type': 'Holiday',
    'schedule_id': scheduleID,
    'user_id_str': '',
    'nurse_name': '',
    'day_1': holidayInit['day_1'],
    'day_2': holidayInit['day_2'],
    'day_3': holidayInit['day_3'],
    'day_4': holidayInit['day_4'],
    'day_5': holidayInit['day_5'],
    'day_6': holidayInit['day_6'],
    'day_7': holidayInit['day_7'],
    'day_8': holidayInit['day_8'],
    'day_9': holidayInit['day_9'],
    'day_10': holidayInit['day_10'],
    'row_type_2': 'Holiday',
    'day_11': holidayInit['day_11'],
    'day_12': holidayInit['day_12'],
    'day_13': holidayInit['day_13'],
    'day_14': holidayInit['day_14'],
    'day_15': holidayInit['day_15'],
    'day_16': holidayInit['day_16'],
    'day_17': holidayInit['day_17'],
    'day_18': holidayInit['day_18'],
    'day_19': holidayInit['day_19'],
    'day_20': holidayInit['day_20'],
    'row_type_3': 'Holiday',
    'day_21': holidayInit['day_21'],
    'day_22': holidayInit['day_22'],
    'day_23': holidayInit['day_23'],
    'day_24': holidayInit['day_24'],
    'day_25': holidayInit['day_25'],
    'day_26': holidayInit['day_26'],
    'day_27': holidayInit['day_27'],
    'day_28': holidayInit['day_28'],
    'day_29': holidayInit['day_29'],
    'day_30': holidayInit['day_30'],
    'row_type_4': 'Holiday'
  }
  #load pto table and update schedule status
  load_pto(scheduleID)
  update_schedule_status(scheduleID,'Submitted Requests: 0')
  #send email
  supervisorsAndSchedulers = get_supervisors_and_schedulers()
  supervisorsList = supervisorsAndSchedulers[0]
  schedulersList = supervisorsAndSchedulers[1]
  ccList = []
  for s in schedulersList:
    ccList.append(s)
  for s in supervisorsList:
    ccList.append(s)
  for row in app_tables.roster.search(
    schedule_id = scheduleID, 
    fte = q.any_of('OPT','FTE (1.0)','FTE (0.9)','FTE (0.8)','FTE (0.7)','FTE (0.6)','FTE (0.5)','FTE (0.4)','FTE (0.3)','FTE (0.2)','FTE (0.1)')
  ):
    emailAddress = row['nurse_email']
    user = app_tables.users.get(email = emailAddress)
    personalEmail = user['personal_email']
    if personalEmail not in ('',None):
      toList = [emailAddress, personalEmail]
    else:
      toList = emailAddress
    anvil.email.send(
      from_name = 'Tachy',
      to = toList,
      cc = ccList,
      subject = '[Schedule] Please submit your requests',
      text = 'Hey! \n \n' + 'It\'s that time again. Log in to submit your requests for the upcoming schedule.',
      html = 'Hey! \n \n' + 'It\'s that time again. <a href="https://fsc.tachy.app">Log in</a> to submit your requests for the upcoming schedule.'
    )

def initialize_request_data(scheduleID,requestData,row):
  nextDay = get_first_day(scheduleID)
  for userID in requestData:
    rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = int(userID))
    nurseName = rosterRow['nurse_name']
    rowType = ['PTO','Request Off','Can\'t do 6','Can\'t do 7','Can\'t do 7*','Can\'t do 8','ACLS']
    for type in rowType:
      requestData[userID].append({
        'row_type': type,
        'schedule_id': scheduleID,
        'user_id_str': userID,
        'nurse_name': nurseName,
        'day_1': 'False',
        'day_2': 'False',
        'day_3': 'False',
        'day_4': 'False',
        'day_5': 'False',
        'day_6': 'False',
        'day_7': 'False',
        'day_8': 'False',
        'day_9': 'False',
        'day_10': 'False',
        'row_type_2': type,
        'day_11': 'False',
        'day_12': 'False',
        'day_13': 'False',
        'day_14': 'False',
        'day_15': 'False',
        'day_16': 'False',
        'day_17': 'False',
        'day_18': 'False',
        'day_19': 'False',
        'day_20': 'False',
        'row_type_3': type,
        'day_21': 'False',
        'day_22': 'False',
        'day_23': 'False',
        'day_24': 'False',
        'day_25': 'False',
        'day_26': 'False',
        'day_27': 'False',
        'day_28': 'False',
        'day_29': 'False',
        'day_30': 'False',
        'row_type_4': type
      })
  row['request_data'] = requestData

@anvil.server.callable
def update_request_data(scheduleID,user,dayString,rowType,value):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = r['request_data']
  userID = str(user['user_id'])
  personData = requestData[userID]
  success = False
  personDataLength = len(personData)
  counter = 0
  while not success and counter < personDataLength:
    dataRow = personData[counter]
    type = dataRow['row_type']
    if type == rowType:
      success = True
    else:
      counter += 1
  dataRow[dayString] = str(value)
  r['request_data'] = requestData

@anvil.server.callable
def update_pto_data(scheduleID,userIDStr,dayString,value):
  #update request data
  r = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = r['request_data']
  personData = requestData[userIDStr]
  success = False
  personDataLength = len(personData)
  counter = 0
  while not success and counter < personDataLength:
    dataRow = personData[counter]
    type = dataRow['row_type']
    if type == 'PTO':
      success = True
    else:
      counter += 1
  dataRow[dayString] = str(value)
  r['request_data'] = requestData

#returns request data for a particular person, separating PTO from all other data
@anvil.server.callable
def show_request_data(scheduleID,user):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = r['request_data']
  userID = str(user['user_id'])
  personData = requestData[userID]
  return personData

#returns pto data for all users from the request data object
@anvil.server.callable
def show_pto_data(scheduleID):
  ptoData = []
  r = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = r['request_data']
  for userID in requestData:
    fte = app_tables.users.get(user_id = int(userID))
    if fte != 'OPT':
      personData = requestData[userID]
      success = False
      personDataLength = len(personData)
      index = 0
      while not success and index < personDataLength:
        dataRow = personData[index]
        type = dataRow['row_type']
        if type == 'PTO':
          success = True
          ptoData.append(dataRow)
        else:
          index += 1
  ptoData = ptodata_to_bool(ptoData)
  ptoData = sorted(ptoData, key = lambda x: x['nurse_name'])
  return ptoData
      
#So... this function takes the request data object from the schedules table and flips it.
#Normally, you search for a person which returns a list of 6 dictionaries, one for acls, one for off, etc
  ##where it's like {row_type: ACLS, day_1: True, day_2: False}
#This function takes that and flips it so it's {day_1: [ACLS], day_2: [7, 7*, 8]}
def get_request_data_by_person(scheduleID,userID):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = r['request_data']
  personData = requestData[userID]
  flippedData = {'day_1': [], 'day_2': [], 'day_3': [], 'day_4': [], 'day_5': [], 'day_6': [], 'day_7': [], 'day_8': [], 'day_9': [], 'day_10': [],
                 'day_11': [], 'day_12': [], 'day_13': [], 'day_14': [], 'day_15': [], 'day_16': [], 'day_17': [], 'day_18': [], 'day_19': [], 'day_20': [],
                 'day_21': [], 'day_22': [], 'day_23': [], 'day_24': [], 'day_25': [], 'day_26': [], 'day_27': [], 'day_28': [], 'day_29': [], 'day_30': []
                }
  for row in personData: 
    type = row['row_type']
    for day in row:
      if 'day_' in day and row[day] == 'True': #if the key is a day key not a row type key and if the day key value is True
        flippedData[day].append(type)
  return flippedData

def get_calendar_dictionary(scheduleID):
  r = app_tables.schedules.get(schedule_id = scheduleID)
  return r['daystring_to_datestring']

#Dump the data in the request_data column in pastschedules if that hasn't already been done
@anvil.server.callable
def load_tables(scheduleID,user):
  userID = user['user_id']
  userIDStr = str(userID)
  sched = app_tables.schedules.get(schedule_id = scheduleID)
  requestData = sched['request_data']
  rosterRow = app_tables.roster.get(schedule_id = scheduleID, user_id = userID)
  nurseName = rosterRow['nurse_name']
  personData = requestData[userIDStr]
  for dataRow in personData:
    rowType = dataRow['row_type']
    for day in dataRow:
      if 'day_' in day and dataRow[day] == 'True':
        if rowType == 'Request Off':
          offDate = daystring_to_date(scheduleID,day)
          app_tables.off.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            off_date = offDate,
            off_date_display = datetime.strptime(str(offDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            included_in_roster_tf = True
          )
        elif rowType == 'ACLS':
          aclsDate = daystring_to_date(scheduleID,day)
          app_tables.acls.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            acls_date = aclsDate,
            acls_date_display = datetime.strptime(str(aclsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            included_in_roster_tf = True
          )
        elif rowType == 'Can\'t do 6':
          shiftsDate = daystring_to_date(scheduleID,day)
          app_tables.shiftsunavailable.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            date = shiftsDate,
            date_display = datetime.strptime(str(shiftsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            shift = 'Shift 6',
            included_in_roster_tf = True
          )
        elif rowType == 'Can\'t do 7':
          shiftsDate = daystring_to_date(scheduleID,day)
          app_tables.shiftsunavailable.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            date = shiftsDate,
            date_display = datetime.strptime(str(shiftsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            shift = 'Shift 7',
            included_in_roster_tf = True
          )
        elif rowType == 'Can\'t do 7*':
          shiftsDate = daystring_to_date(scheduleID,day)
          app_tables.shiftsunavailable.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            date = shiftsDate,
            date_display = datetime.strptime(str(shiftsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            shift = 'Shift 7*',
            included_in_roster_tf = True
          )
        elif rowType == 'Can\'t do 8':
          shiftsDate = daystring_to_date(scheduleID,day)
          app_tables.shiftsunavailable.add_row(
            schedule_id = scheduleID,
            user_id = userID,
            nurse_name = nurseName,
            date = shiftsDate,
            date_display = datetime.strptime(str(shiftsDate),'%Y-%m-%d').strftime('%b %d, %Y'),
            shift = 'Shift 8',
            included_in_roster_tf = True
          )

#returns [tf,tf] 
#the first tf is if the user is required to submit a request form
#the second tf is if the user has submitted their requests form
@anvil.server.callable
def is_request_needed_submitted(scheduleID,user):
  userID = str(user['user_id'])
  r = app_tables.schedules.get(schedule_id = scheduleID)
  checkSubmitted = r['check_submitted']
  if userID in checkSubmitted:
    if checkSubmitted[userID] == 'False':
      isSubmitted = False
    else:
      isSubmitted = True
    return [True, isSubmitted]
  else:
    return [False, False]

#update check_submitted in pastschedules to True for the user
#increment number of requests submitted,
#return number of requests submitted and needed
@anvil.server.callable
def submit_request(scheduleID,user):
  fte = user['fte']
  if 'FTE' in fte:
    load_tables(scheduleID,user)
  r = app_tables.schedules.get(schedule_id = scheduleID)
  checkSubmitted = r['check_submitted']
  userID = str(user['user_id'])
  checkSubmitted[userID] = 'True' 
  r['check_submitted'] = checkSubmitted #update that the user submitted their request
  r['requests_submitted'] += 1 #increment the stored number of requests submitted
  numRequestsSubmitted = r['requests_submitted']
  numRequestsNeeded = r['requests_needed']
  if numRequestsSubmitted == numRequestsNeeded:
    status = 'Scheduler to create schedule'
  else:
    status = 'Submitted Requests: ' + str(numRequestsSubmitted) + '/' + str(numRequestsNeeded)
  update_schedule_status(scheduleID,status) #update status
  send_request_email(scheduleID,user,numRequestsSubmitted,numRequestsNeeded) #send email

#convert request data which has string values to have boolean values
@anvil.server.callable
def requestdata_to_bool(personData):
  for dataRow in personData:
    for day in dataRow:
      if dataRow[day] == 'False':
        dataRow[day] = False
      elif dataRow[day] == 'True':
        dataRow[day] = True
  return personData

#convert true/false strings to boolean in ptoData
def ptodata_to_bool(ptoData):
  for dataRow in ptoData:
    for day in dataRow:
      if dataRow[day] == 'False':
        dataRow[day] = False
      elif dataRow[day] == 'True':
        dataRow[day] = True
  return ptoData
