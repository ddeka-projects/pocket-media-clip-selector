const cases=[
 ["5",5,"0:05"],["32",32,"0:32"],["105",65,"1:05"],["332",212,"3:32"],
 ["1742",1062,"17:42"],["6000",3600,"1:00:00"],["11432",4472,"1:14:32"],
 ["123456",45296,"12:34:56"],["17:42",1062,"17:42"],["1:14:32",4472,"1:14:32"],
 ["0",0,"0:00"],["0005",5,"0:05"],[" 1742 ",1062,"17:42"],["75:32",4532,"1:15:32"],
 ["9900",5940,"1:39:00"],["9995959",3599999,"999:59:59"],["59999:59",3599999,"999:59:59"],
 ["0:0",0,"0:00"],["00001742",1062,"17:42"]
];
for(const [raw,seconds,label] of cases){equal(parseTimestamp(raw),seconds,"parse "+raw);equal(formatBookmark(seconds),label,"display "+raw);equal(parseTimestamp(compactTimestamp(seconds)),seconds,"compact time roundtrip");}
for(const raw of ["1768","1:75:32","abc","-4",""," ","60","0060","16000","06000","0:60:00","1:14:60","17:68","1:2:3:4","1.5","1e3","NaN","Infinity","10000000","60000:00","9".repeat(1000),"9999999999999999","１２３４"]){
 let rejected=false;try{parseTimestamp(raw);}catch{rejected=true;}assert(rejected,"invalid timestamp must be rejected: "+raw);
}
equal(formatBookmark(50.875),"0:50","ordinary list omits fractional precision");
equal(formatBookmark(NaN),"—","invalid display");
