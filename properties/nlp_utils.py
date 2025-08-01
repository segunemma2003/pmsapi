"""
Simplified NLP Utilities for Property Extraction
Focus on reliable, direct extraction without over-engineering
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

@dataclass
class ExtractedEntity:
    """Represents an extracted entity from user input."""
    text: str
    label: str
    confidence: float

class SimplifiedNLPProcessor:
    """Simplified NLP processor focused on reliable property extraction."""
    
    def __init__(self):
        """Initialize with essential patterns only."""
        
        # Property types with priority order
        self.PROPERTY_TYPES = [
            ('house', ['house', 'home', 'single family']),
            ('apartment', ['apartment', 'apt', 'flat', 'condo', 'unit']),
            ('villa', ['villa', 'mansion']),
            ('cabin', ['cabin', 'cottage', 'chalet']),
            ('loft', ['loft', 'studio']),
        ]
        
        # Place types
        self.PLACE_TYPES = [
            ('entire_place', ['entire place', 'whole place', 'full place', 'complete place']),
            ('private_room', ['private room', 'own room', 'bedroom']),
            ('shared_room', ['shared room', 'shared space']),
        ]
        
        # Common cities (expandable)
        self.COMMON_CITIES = {
            # Major US Cities
            'new york', 'los angeles', 'chicago', 'houston', 'phoenix', 'philadelphia',
            'san antonio', 'san diego', 'dallas', 'san jose', 'austin', 'jacksonville',
            'san francisco', 'indianapolis', 'seattle', 'denver', 'washington', 'boston',
            'el paso', 'detroit', 'nashville', 'portland', 'oklahoma city', 'las vegas',
            'louisville', 'baltimore', 'milwaukee', 'albuquerque', 'tucson', 'fresno',
            'sacramento', 'kansas city', 'mesa', 'virginia beach', 'atlanta', 'colorado springs',
            'omaha', 'raleigh', 'miami', 'oakland', 'minneapolis', 'tulsa', 'cleveland',
            'wichita', 'arlington', 'new orleans', 'bakersfield', 'tampa', 'honolulu',
            'aurora', 'anaheim', 'santa ana', 'st. louis', 'riverside', 'corpus christi',
            'lexington', 'pittsburgh', 'anchorage', 'stockton', 'cincinnati', 'saint paul',
            
            # Major Canadian Cities
            'toronto', 'vancouver', 'montreal', 'calgary', 'ottawa', 'edmonton',
            'mississauga', 'winnipeg', 'quebec city', 'hamilton', 'brampton', 'surrey',
            'laval', 'halifax', 'london', 'markham', 'vaughan', 'gatineau', 'saskatoon',
            'longueuil', 'burnaby', 'regina', 'richmond', 'richmond hill', 'oakville',
            'burlington', 'greater sudbury', 'sherbrooke', 'oshawa', 'saguenay',
            
            # Major UK Cities
            'london', 'manchester', 'birmingham', 'leeds', 'glasgow', 'liverpool',
            'newcastle', 'sheffield', 'bristol', 'cardiff', 'edinburgh', 'leicester',
            'coventry', 'bradford', 'belfast', 'nottingham', 'hull', 'plymouth',
            'stoke-on-trent', 'wolverhampton', 'derby', 'swansea', 'southampton',
            'salford', 'aberdeen', 'westminster', 'portsmouth', 'york', 'peterborough',
            'dundee', 'lancaster', 'oxford', 'newport', 'preston', 'st albans',
            'canterbury', 'winchester', 'gloucester', 'exeter', 'bath', 'durham',
            
            # Major Australian Cities
            'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide', 'canberra',
            'gold coast', 'newcastle', 'wollongong', 'logan city', 'geelong', 'hobart',
            'townsville', 'cairns', 'darwin', 'toowoomba', 'ballarat', 'bendigo',
            'albury', 'launceston', 'mackay', 'rockhampton', 'bunbury', 'coffs harbour',
            'bundaberg', 'wagga wagga', 'hervey bay', 'mildura', 'shepparton', 'port macquarie',
            
            # Major European Cities
            'paris', 'madrid', 'rome', 'berlin', 'vienna', 'hamburg', 'barcelona',
            'munich', 'milan', 'naples', 'turin', 'cologne', 'frankfurt', 'stuttgart',
            'dortmund', 'essen', 'leipzig', 'bremen', 'dresden', 'hanover', 'nuremberg',
            'amsterdam', 'rotterdam', 'the hague', 'utrecht', 'eindhoven', 'tilburg',
            'almere', 'groningen', 'breda', 'nijmegen', 'enschede', 'haarlem',
            'brussels', 'antwerp', 'ghent', 'charleroi', 'liege', 'bruges', 'namur',
            'zurich', 'geneva', 'basel', 'lausanne', 'bern', 'winterthur', 'lucerne',
            'oslo', 'bergen', 'stavanger', 'trondheim', 'drammen', 'fredrikstad',
            'stockholm', 'gothenburg', 'malmo', 'uppsala', 'vasteras', 'orebro',
            'copenhagen', 'aarhus', 'odense', 'aalborg', 'esbjerg', 'randers',
            'helsinki', 'espoo', 'tampere', 'vantaa', 'oulu', 'turku', 'jyvaskyla',
            'athens', 'thessaloniki', 'patras', 'heraklion', 'larissa', 'volos',
            'dublin', 'cork', 'limerick', 'waterford', 'galway', 'drogheda',
            'prague', 'brno', 'ostrava', 'plzen', 'liberec', 'olomouc',
            'budapest', 'debrecen', 'miskolc', 'szeged', 'pecs', 'gyor',
            'warsaw', 'krakow', 'lodz', 'wroclaw', 'poznan', 'gdansk', 'szczecin',
            'bydgoszcz', 'lublin', 'katowice', 'bialystok', 'gdynia', 'czestochowa',
            'bucharest', 'cluj-napoca', 'timisoara', 'iasi', 'constanta', 'craiova',
            'brasov', 'galati', 'ploiesti', 'oradea', 'braila', 'arad',
            'lisbon', 'porto', 'amadora', 'braga', 'setubal', 'coimbra',
            
            # Major Asian Cities
            'tokyo', 'osaka', 'yokohama', 'nagoya', 'sapporo', 'fukuoka', 'kobe',
            'kyoto', 'kawasaki', 'saitama', 'hiroshima', 'sendai', 'chiba', 'kitakyushu',
            'sakai', 'niigata', 'hamamatsu', 'okayama', 'sagamihara', 'kumamoto',
            'beijing', 'shanghai', 'guangzhou', 'shenzhen', 'tianjin', 'wuhan',
            'dongguan', 'chengdu', 'nanjing', 'foshan', 'shenyang', 'qingdao',
            'xian', 'dalian', 'zhengzhou', 'shantou', 'jinan', 'changchun',
            'harbin', 'kunming', 'changsha', 'taiyuan', 'shijiazhuang', 'xuzhou',
            'seoul', 'busan', 'incheon', 'daegu', 'daejeon', 'gwangju', 'suwon',
            'ulsan', 'changwon', 'goyang', 'yongin', 'seongnam', 'bucheon',
            'mumbai', 'delhi', 'bangalore', 'hyderabad', 'ahmedabad', 'chennai',
            'kolkata', 'surat', 'pune', 'jaipur', 'lucknow', 'kanpur', 'nagpur',
            'indore', 'thane', 'bhopal', 'visakhapatnam', 'pimpri-chinchwad', 'patna',
            'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad',
            'meerut', 'rajkot', 'kalyan-dombivali', 'vasai-virar', 'varanasi', 'srinagar',
            'dhaka', 'chittagong', 'sylhet', 'rajshahi', 'comilla', 'rangpur',
            'karachi', 'lahore', 'faisalabad', 'rawalpindi', 'gujranwala', 'peshawar',
            'multan', 'hyderabad', 'islamabad', 'quetta', 'bahawalpur', 'sargodha',
            'bangkok', 'chiang mai', 'phuket', 'pattaya', 'hat yai', 'nakhon ratchasima',
            'udon thani', 'surat thani', 'khon kaen', 'nakhon si thammarat',
            'manila', 'quezon city', 'davao', 'caloocan', 'cebu city', 'zamboanga',
            'antipolo', 'taguig', 'pasig', 'cagayan de oro', 'paranaque', 'valenzuela',
            'jakarta', 'surabaya', 'medan', 'bandung', 'bekasi', 'palembang',
            'tangerang', 'makassar', 'south tangerang', 'depok', 'semarang', 'batam',
            'bandar lampung', 'bogor', 'pekanbaru', 'padang', 'malang', 'samarinda',
            'kuala lumpur', 'george town', 'ipoh', 'shah alam', 'petaling jaya',
            'johor bahru', 'seremban', 'kuching', 'kota kinabalu', 'sandakan',
            'singapore', 'ho chi minh city', 'hanoi', 'da nang', 'can tho', 'bien hoa',
            'hue', 'nha trang', 'buon ma thuot', 'vung tau', 'nam dinh', 'vinh',
            
            # Major African Cities
            'lagos', 'abuja', 'kano', 'ibadan', 'port harcourt', 'benin city',
            'maiduguri', 'zaria', 'aba', 'jos', 'ilorin', 'oyo', 'enugu', 'abeokuta',
            'onitsha', 'warri', 'okene', 'calabar', 'uyo', 'katsina', 'ado-ekiti',
            'ogbomoso', 'akure', 'bauchi', 'kumo', 'makurdi', 'minna', 'effon alaiye',
            'ilesa', 'shaki', 'ondo', 'iseyin', 'kishi', 'katsina-ala', 'gusau',
            'cairo', 'alexandria', 'giza', 'shubra el-kheima', 'port said', 'suez',
            'luxor', 'mansoura', 'el-mahalla el-kubra', 'tanta', 'asyut', 'ismailia',
            'fayyum', 'zagazig', 'aswan', 'damietta', 'damanhur', 'minya',
            'cape town', 'johannesburg', 'durban', 'pretoria', 'port elizabeth',
            'pietermaritzburg', 'benoni', 'tembisa', 'east london', 'vereeniging',
            'bloemfontein', 'boksburg', 'welkom', 'newcastle', 'krugersdorp',
            'diepsloot', 'botshabelo', 'brakpan', 'witbank', 'oberholzer',
            'casablanca', 'rabat', 'fes', 'marrakech', 'agadir', 'tangier',
            'meknes', 'oujda', 'kenitra', 'tetouan', 'safi', 'mohammedia',
            'khouribga', 'el jadida', 'beni mellal', 'nador', 'taza', 'settat',
            'tunis', 'sfax', 'sousse', 'ettadhamen', 'kairouan', 'bizerte',
            'gabès', 'aryanah', 'gafsa', 'kasserine', 'monastir', 'ben arous',
            'algiers', 'oran', 'constantine', 'annaba', 'blida', 'batna',
            'djelfa', 'setif', 'sidi bel abbes', 'biskra', 'tebessa', 'el oued',
            'skikda', 'tiaret', 'bejaia', 'tlemcen', 'ouargla', 'mostaganem',
            'addis ababa', 'dire dawa', 'mek\'ele', 'gondar', 'hawassa', 'bahir dar',
            'dessie', 'jimma', 'jijiga', 'shashamane', 'nekemte', 'bishoftu',
            'nairobi', 'mombasa', 'nakuru', 'eldoret', 'kisumu', 'thika',
            'malindi', 'kitale', 'garissa', 'kakamega', 'machakos', 'lamu',
            'accra', 'kumasi', 'tamale', 'cape coast', 'sekondi-takoradi', 'koforidua',
            'wa', 'ho', 'techiman', 'obuasi', 'tema', 'madina', 'adenta', 'kasoa',
            'dakar', 'touba', 'thies', 'kaolack', 'saint-louis', 'mbour',
            'rufisque', 'ziguinchor', 'louga', 'diourbel', 'tambacounda', 'richard toll',
            'kampala', 'gulu', 'lira', 'mbarara', 'jinja', 'bwizibwera',
            'mukono', 'kasese', 'masaka', 'entebbe', 'njeru', 'kitgum',
            'dar es salaam', 'mwanza', 'arusha', 'dodoma', 'mbeya', 'morogoro',
            'tanga', 'kahama', 'tabora', 'kigoma', 'moshi', 'musoma',
            'lusaka', 'kitwe', 'ndola', 'kabwe', 'chingola', 'mufulira',
            'livingstone', 'luanshya', 'kasama', 'chipata', 'mazabuka', 'choma',
            
            # Major South American Cities
            'sao paulo', 'rio de janeiro', 'salvador', 'brasilia', 'fortaleza',
            'belo horizonte', 'manaus', 'curitiba', 'recife', 'goiania',
            'porto alegre', 'guarulhos', 'campinas', 'sao luis', 'sao goncalo',
            'maceio', 'duque de caxias', 'natal', 'teresina', 'campo grande',
            'nova iguacu', 'sao bernardo do campo', 'joao pessoa', 'santo andre',
            'osasco', 'jaboatao dos guararapes', 'sao jose dos campos', 'ribeirao preto',
            'uberlandia', 'sorocaba', 'contagem', 'aracaju', 'feira de santana',
            'cuiaba', 'joinville', 'juiz de fora', 'londrina', 'aparecida de goiania',
            'buenos aires', 'cordoba', 'rosario', 'mendoza', 'tucuman',
            'la plata', 'mar del plata', 'quilmes', 'salta', 'santa fe',
            'san juan', 'resistencia', 'santiago del estero', 'corrientes', 'posadas',
            'neuquen', 'bahia blanca', 'parana', 'formosa', 'san luis',
            'lima', 'arequipa', 'trujillo', 'chiclayo', 'huancayo', 'piura',
            'iquitos', 'cusco', 'chimbote', 'tacna', 'juliaca', 'ica',
            'sullana', 'ayacucho', 'chincha alta', 'huanuco', 'tarapoto', 'puno',
            'bogota', 'medellin', 'cali', 'barranquilla', 'cartagena', 'cucuta',
            'bucaramanga', 'pereira', 'santa marta', 'ibague', 'soacha', 'pasto',
            'manizales', 'neiva', 'soledad', 'armenia', 'villavicencio', 'valledupar',
            'santiago', 'valparaiso', 'concepcion', 'la serena', 'antofagasta',
            'temuco', 'rancagua', 'talca', 'arica', 'chilian', 'iquique',
            'los angeles', 'puerto montt', 'coquimbo', 'osorno', 'valdivia', 'punta arenas',
            'caracas', 'maracaibo', 'valencia', 'barquisimeto', 'maracay',
            'ciudad guayana', 'san cristobal', 'maturin', 'ciudad bolivar', 'cumana',
            'merida', 'barcelona', 'punto fijo', 'los teques', 'guarenas',
            'quito', 'guayaquil', 'cuenca', 'santo domingo', 'machala',
            'duran', 'manta', 'portoviejo', 'ambato', 'esmeraldas',
            'riobamba', 'milagro', 'ibarra', 'loja', 'quininde',
            'la paz', 'santa cruz', 'cochabamba', 'oruro', 'sucre', 'tarija',
            'potosi', 'sacaba', 'montero', 'trinidad', 'el alto', 'cobija',
            'montevideo', 'salto', 'paysandu', 'las piedras', 'rivera', 'maldonado',
            'tacuarembo', 'melo', 'mercedes', 'artigas', 'minas', 'san jose de mayo',
            'asuncion', 'ciudad del este', 'san lorenzo', 'lambare', 'fernando de la mora',
            'nemby', 'pedro juan caballero', 'encarnacion', 'mariano roque alonso',
            'villa elisa', 'san antonio', 'capiata', 'luque', 'coronel oviedo',
            'georgetown', 'linden', 'new amsterdam', 'anna regina', 'bartica',
            'paramaribo', 'lelydorp', 'brokopondo', 'nieuw nickerie', 'moengo',
            'cayenne', 'saint-laurent-du-maroni', 'kourou', 'remire-montjoly', 'matoury'
        }
        
        # Common countries
        self.COMMON_COUNTRIES = {
            # North America
            'united states', 'usa', 'us', 'canada', 'mexico',
            
            # Europe
            'united kingdom', 'uk', 'england', 'scotland', 'wales', 'northern ireland',
            'france', 'germany', 'italy', 'spain', 'netherlands', 'switzerland',
            'belgium', 'austria', 'sweden', 'norway', 'denmark', 'finland',
            'poland', 'czech republic', 'slovakia', 'hungary', 'romania', 'bulgaria',
            'croatia', 'serbia', 'bosnia and herzegovina', 'montenegro', 'slovenia',
            'albania', 'macedonia', 'greece', 'turkey', 'portugal', 'ireland',
            'iceland', 'luxembourg', 'malta', 'cyprus', 'estonia', 'latvia',
            'lithuania', 'belarus', 'ukraine', 'moldova', 'russia',
            
            # Asia
            'china', 'japan', 'south korea', 'north korea', 'india', 'pakistan',
            'bangladesh', 'sri lanka', 'nepal', 'bhutan', 'maldives', 'afghanistan',
            'iran', 'iraq', 'syria', 'lebanon', 'jordan', 'israel', 'palestine',
            'saudi arabia', 'uae', 'qatar', 'kuwait', 'bahrain', 'oman', 'yemen',
            'thailand', 'vietnam', 'cambodia', 'laos', 'myanmar', 'malaysia',
            'singapore', 'indonesia', 'philippines', 'brunei', 'east timor',
            'mongolia', 'kazakhstan', 'uzbekistan', 'turkmenistan', 'kyrgyzstan',
            'tajikistan', 'armenia', 'azerbaijan', 'georgia',
            
            # Africa
            'nigeria', 'ghana', 'kenya', 'south africa', 'egypt', 'morocco',
            'algeria', 'tunisia', 'libya', 'sudan', 'south sudan', 'ethiopia',
            'somalia', 'djibouti', 'eritrea', 'uganda', 'tanzania', 'rwanda',
            'burundi', 'democratic republic of congo', 'republic of congo',
            'central african republic', 'chad', 'cameroon', 'equatorial guinea',
            'gabon', 'sao tome and principe', 'cape verde', 'guinea-bissau',
            'guinea', 'sierra leone', 'liberia', 'ivory coast', 'burkina faso',
            'mali', 'senegal', 'mauritania', 'gambia', 'niger', 'benin', 'togo',
            'zambia', 'zimbabwe', 'botswana', 'namibia', 'angola', 'mozambique',
            'malawi', 'madagascar', 'mauritius', 'seychelles', 'comoros',
            'lesotho', 'swaziland', 'eswatini',
            
            # Oceania
            'australia', 'new zealand', 'fiji', 'papua new guinea', 'solomon islands',
            'vanuatu', 'samoa', 'tonga', 'kiribati', 'tuvalu', 'nauru', 'palau',
            'micronesia', 'marshall islands',
            
            # South America
            'brazil', 'argentina', 'chile', 'peru', 'colombia', 'venezuela',
            'ecuador', 'bolivia', 'paraguay', 'uruguay', 'guyana', 'suriname',
            'french guiana',
            
            # Central America and Caribbean
            'guatemala', 'belize', 'el salvador', 'honduras', 'nicaragua',
            'costa rica', 'panama', 'cuba', 'jamaica', 'haiti', 'dominican republic',
            'bahamas', 'barbados', 'trinidad and tobago', 'grenada', 'saint lucia',
            'saint vincent and the grenadines', 'antigua and barbuda',
            'dominica', 'saint kitts and nevis'
        }
        
        # Address indicators (to avoid extracting numbers from addresses)
        self.ADDRESS_INDICATORS = [
            # Street types
            'street', 'avenue', 'road', 'drive', 'lane', 'boulevard', 'way',
            'court', 'place', 'circle', 'terrace', 'plaza', 'square', 'parkway',
            'crescent', 'close', 'grove', 'gardens', 'mews', 'walk', 'row',
            'hill', 'rise', 'view', 'heights', 'ridge', 'green', 'common',
            'broadway', 'highway', 'freeway', 'expressway', 'turnpike', 'route',
            'trail', 'path', 'alley', 'passage', 'arcade', 'mall', 'strand',
            
            # Abbreviations
            'st', 'ave', 'rd', 'dr', 'ln', 'blvd', 'ct', 'pl', 'cir', 'ter',
            'plz', 'sq', 'pkwy', 'cres', 'cl', 'gr', 'gdns', 'hwy', 'fwy',
            'expy', 'tpke', 'rt', 'rte', 'tr', 'pth', 'aly', 'psge', 'arc',
            
            # Building/location types
            'apartment', 'apt', 'suite', 'unit', 'floor', 'building', 'tower',
            'complex', 'residence', 'house', 'home', 'villa', 'mansion', 'estate',
            'cottage', 'cabin', 'bungalow', 'townhouse', 'condominium', 'condo',
            'loft', 'studio', 'penthouse', 'duplex', 'triplex', 'quadplex',
            
            # Directional indicators
            'north', 'south', 'east', 'west', 'northeast', 'northwest',
            'southeast', 'southwest', 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw',
            'northern', 'southern', 'eastern', 'western', 'upper', 'lower',
            
            # Address components
            'block', 'lot', 'parcel', 'tract', 'subdivision', 'development',
            'neighborhood', 'district', 'sector', 'zone', 'area', 'region',
            'locality', 'suburb', 'borough', 'ward', 'parish', 'county',
            'province', 'state', 'territory', 'prefecture', 'canton',
            
            # Postal/zip indicators
            'zip', 'zipcode', 'postal', 'postcode', 'po box', 'p.o. box',
            'mail stop', 'mailstop', 'box', 'drawer', 'rural route', 'rr',
            
            # International address terms
            'rue', 'via', 'strada', 'calle', 'carrera', 'avenida', 'rua',
            'strasse', 'gasse', 'platz', 'weg', 'allee', 'damm', 'ring',
            'kai', 'cho', 'dori', 'machi', 'ku', 'shi', 'gun', 'ken',
            'dong', 'lu', 'jie', 'qu', 'shi', 'xian', 'sheng'
        ]
    
    def extract_property_data(self, text: str, conversation_context: Dict = None) -> Dict[str, Any]:
        """Main extraction method with conversation context."""
        
        print(f"🔍 NLP Processing: '{text}'")
        
        extracted_entities = []
        extracted_data = {}
        
        # Clean and normalize text
        text = text.strip()
        text_lower = text.lower()
        
        # Check if this looks like an address (skip number extraction if so)
        has_address_indicators = any(indicator in text_lower for indicator in self.ADDRESS_INDICATORS)
        
        # 1. Extract property type
        property_type = self._extract_property_type(text_lower)
        if property_type:
            extracted_data['property_type'] = property_type
            extracted_entities.append(ExtractedEntity(property_type, 'property_type', 0.9))
        
        # 2. Extract place type
        place_type = self._extract_place_type(text_lower)
        if place_type:
            extracted_data['place_type'] = place_type
            extracted_entities.append(ExtractedEntity(place_type, 'place_type', 0.9))
        
        # 3. Extract location (city/country)
        city, country = self._extract_location(text, text_lower)
        if city:
            extracted_data['city'] = city
            extracted_entities.append(ExtractedEntity(city, 'city', 0.8))
        if country:
            extracted_data['country'] = country
            extracted_entities.append(ExtractedEntity(country, 'country', 0.8))
        
        # 4. Extract numbers (only if no address indicators)
        if not has_address_indicators:
            numbers_data = self._extract_numbers(text, text_lower)
            extracted_data.update(numbers_data)
            
            for key, value in numbers_data.items():
                extracted_entities.append(ExtractedEntity(str(value), key, 0.8))
        
        # 5. Extract boolean policies
        policies = self._extract_policies(text_lower)
        extracted_data.update(policies)
        
        for key, value in policies.items():
            extracted_entities.append(ExtractedEntity(str(value), key, 0.7))
        
        # 6. Extract times
        times = self._extract_times(text)
        extracted_data.update(times)
        
        for key, value in times.items():
            extracted_entities.append(ExtractedEntity(value, key, 0.8))
        
        # 7. Detect title/description
        title_desc = self._detect_title_description(text)
        extracted_data.update(title_desc)
        
        for key, value in title_desc.items():
            extracted_entities.append(ExtractedEntity(value, key, 0.7))
        
        print(f"✅ NLP Extracted: {extracted_data}")
        
        return {
            'extracted_entities': [
                {'text': e.text, 'label': e.label, 'confidence': e.confidence} 
                for e in extracted_entities
            ],
            'extracted_data': extracted_data,
            'user_intent': 'provide_information',
            'sentiment_analysis': {'sentiment': 'positive', 'confidence': 0.8},
            'confidence': 0.9 if extracted_data else 0.3
        }
    
    def _extract_property_type(self, text_lower: str) -> Optional[str]:
        """Extract property type with priority order."""
        for prop_type, keywords in self.PROPERTY_TYPES:
            for keyword in keywords:
                if keyword in text_lower:
                    print(f"🏠 Found property type: {prop_type} (keyword: {keyword})")
                    return prop_type
        return None
    
    def _extract_place_type(self, text_lower: str) -> Optional[str]:
        """Extract place type."""
        for place_type, keywords in self.PLACE_TYPES:
            for keyword in keywords:
                if keyword in text_lower:
                    print(f"🏡 Found place type: {place_type} (keyword: {keyword})")
                    return place_type
        return None
    
    def _extract_location(self, text: str, text_lower: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract city and country."""
        city = None
        country = None
        
        # Look for "in [location]" patterns
        location_patterns = [
            r'\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'\bat\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'\blocated in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        ]
        
        for pattern in location_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                location = match.group(1).lower()
                
                # Check if it's a known city
                if location in self.COMMON_CITIES:
                    city = match.group(1).title()
                    print(f"🌆 Found city: {city}")
                
                # Check if it's a known country
                elif location in self.COMMON_COUNTRIES:
                    country = match.group(1).title()
                    print(f"🌍 Found country: {country}")
        
        # Handle comma-separated "City, Country" format
        comma_pattern = r'\b([A-Z][a-z]+),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        comma_matches = re.finditer(comma_pattern, text)
        
        for match in comma_matches:
            potential_city = match.group(1).lower()
            potential_country = match.group(2).lower()
            
            if potential_city in self.COMMON_CITIES and potential_country in self.COMMON_COUNTRIES:
                city = match.group(1).title()
                country = match.group(2).title()
                print(f"🌆🌍 Found city, country: {city}, {country}")
                break
        
        return city, country
    
    def _extract_numbers(self, text: str, text_lower: str) -> Dict[str, int]:
        """Extract numbers with context awareness."""
        numbers = {}
        
        # Guest capacity
        guest_patterns = [
            r'(\d+)\s*(guest|guests|people|person)',
            r'accommodate[s]?\s*(\d+)',
            r'capacity\s*(?:of\s*)?(\d+)'
        ]
        
        for pattern in guest_patterns:
            match = re.search(pattern, text_lower)
            if match:
                guests = int(match.group(-1))
                if 1 <= guests <= 20:  # Reasonable range
                    numbers['max_guests'] = guests
                    print(f"👥 Found guests: {guests}")
                break
        
        # Bedrooms
        bedroom_patterns = [
            r'(\d+)\s*(bedroom|bedrooms|bed|beds)',
            r'(\d+)[-\s]*(?:br|bedroom)'
        ]
        
        for pattern in bedroom_patterns:
            match = re.search(pattern, text_lower)
            if match:
                bedrooms = int(match.group(1))
                if 0 <= bedrooms <= 20:
                    numbers['bedrooms'] = bedrooms
                    print(f"🛏️ Found bedrooms: {bedrooms}")
                break
        
        # Bathrooms  
        bathroom_patterns = [
            r'(\d+)\s*(bathroom|bathrooms|bath|baths)',
            r'(\d+)[-\s]*(?:ba|bathroom)'
        ]
        
        for pattern in bathroom_patterns:
            match = re.search(pattern, text_lower)
            if match:
                bathrooms = int(match.group(1))
                if 0 <= bathrooms <= 20:
                    numbers['bathrooms'] = bathrooms
                    print(f"🚿 Found bathrooms: {bathrooms}")
                break
        
        # Price (only when clearly indicated)
        price_indicators = ['$', 'price', 'cost', 'rate', 'charge', 'per night', 'nightly']
        has_price_indicator = any(indicator in text_lower for indicator in price_indicators)
        
        if has_price_indicator:
            price_patterns = [
                r'\$(\d+)',
                r'(\d+)\s*(?:dollars?|usd)',
                r'(?:price|cost|rate|charge)\s*(?:is\s*)?\$?(\d+)',
                r'(\d+)\s*(?:per night|nightly)'
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    price = int(match.group(1))
                    if 10 <= price <= 10000:  # Reasonable range
                        numbers['display_price'] = price
                        numbers['price_per_night'] = price
                        print(f"💰 Found price: ${price}")
                    break
        
        return numbers
    
    def _extract_policies(self, text_lower: str) -> Dict[str, bool]:
        """Extract boolean policies."""
        policies = {}
        
        # Smoking policy
        if 'no smoking' in text_lower or 'smoking not allowed' in text_lower:
            policies['smoking_allowed'] = False
        elif 'smoking allowed' in text_lower or 'smoking ok' in text_lower:
            policies['smoking_allowed'] = True
        
        # Pet policy
        if 'no pets' in text_lower or 'pets not allowed' in text_lower:
            policies['pets_allowed'] = False
        elif 'pets allowed' in text_lower or 'pet friendly' in text_lower:
            policies['pets_allowed'] = True
        
        # Events policy
        if 'no events' in text_lower or 'no parties' in text_lower:
            policies['events_allowed'] = False
        elif 'events allowed' in text_lower or 'parties ok' in text_lower:
            policies['events_allowed'] = True
        
        # Children policy
        if 'no children' in text_lower or 'adults only' in text_lower:
            policies['children_welcome'] = False
        elif 'children welcome' in text_lower or 'family friendly' in text_lower:
            policies['children_welcome'] = True
        
        return policies
    
    def _extract_times(self, text: str) -> Dict[str, str]:
        """Extract check-in/check-out times."""
        times = {}
        
        # Check-in time
        checkin_patterns = [
            r'check[-\s]*in\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}:\d{2})',
            r'check[-\s]*in\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}\s*(?:am|pm))',
            r'arrive\s*(?:at\s*)?(\d{1,2}:\d{2})',
            r'arrive\s*(?:at\s*)?(\d{1,2}\s*(?:am|pm))'
        ]
        
        for pattern in checkin_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                time_str = self._normalize_time(match.group(1))
                if time_str:
                    times['check_in_time_start'] = time_str
                    print(f"⏰ Found check-in time: {time_str}")
                break
        
        # Check-out time
        checkout_patterns = [
            r'check[-\s]*out\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}:\d{2})',
            r'check[-\s]*out\s*(?:time|at|is)?\s*(?:is\s*)?(\d{1,2}\s*(?:am|pm))',
            r'leave\s*(?:by\s*)?(\d{1,2}:\d{2})',
            r'leave\s*(?:by\s*)?(\d{1,2}\s*(?:am|pm))'
        ]
        
        for pattern in checkout_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                time_str = self._normalize_time(match.group(1))
                if time_str:
                    times['check_out_time'] = time_str
                    print(f"⏰ Found check-out time: {time_str}")
                break
        
        return times
    
    def _normalize_time(self, time_str: str) -> Optional[str]:
        """Normalize time to HH:MM format."""
        time_str = time_str.lower().strip()
        
        # Handle "3pm", "3 pm" format
        am_pm_match = re.match(r'(\d{1,2})\s*(am|pm)', time_str)
        if am_pm_match:
            hour = int(am_pm_match.group(1))
            period = am_pm_match.group(2)
            
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            
            return f"{hour:02d}:00"
        
        # Handle "15:00" format
        if re.match(r'^\d{1,2}:\d{2}$', time_str):
            return time_str
        
        return None
    
    def _detect_title_description(self, text: str) -> Dict[str, str]:
        """Detect if text is a title or description."""
        content = {}
        text_lower = text.lower().strip()
        
        # Title detection (short, descriptive text)
        title_indicators = [
            'cozy', 'beautiful', 'modern', 'charming', 'luxury', 'perfect',
            'stunning', 'amazing', 'lovely', 'comfortable', 'spacious',
            'quiet', 'central', 'convenient', 'elegant', 'stylish'
        ]
        
        if (10 <= len(text) <= 100 and 
            not text.endswith('?') and
            any(indicator in text_lower for indicator in title_indicators)):
            content['title'] = text.strip()
            print(f"✨ Detected title: {text[:50]}...")
        
        # Description detection (longer, descriptive text)
        description_indicators = [
            'property', 'place', 'home', 'guests', 'stay', 'located',
            'features', 'offers', 'includes', 'amenities', 'perfect for'
        ]
        
        if (50 <= len(text) <= 1000 and
            len(text.split()) >= 10 and
            any(indicator in text_lower for indicator in description_indicators)):
            content['description'] = text.strip()
            print(f"📝 Detected description: {text[:50]}...")
        
        return content

# Global processor instance
nlp_processor = SimplifiedNLPProcessor()