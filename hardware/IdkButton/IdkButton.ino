#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Wire.h>

Arduino_LED_Matrix matrix;
const int RED_LED_PIN=D8;
// 0 idle, 1 recording, 2 ASR, 3 LLM, 4 ready, 5 speaking, 6 error
int uiState=0, selected=0, answerCount=0, address=0;
arduino::ZephyrI2C* bus=&Wire1;
int busIndex=-1;
int16_t position=0, lastPosition=0;
int32_t rotations=0;
uint32_t clicks=0, holds=0, frames=0, readErrors=0;
bool knobOk=false, pressed=false, initialized=false, rawPressed=false, held=false;
bool redLed=false;
unsigned long changedAt=0, downAt=0, lastScan=0;
uint32_t frameHash=0; int litPixels=0;

void scanKnob(){
 address=0;busIndex=-1;
 arduino::ZephyrI2C* buses[]={&Wire1,&Wire2,&Wire};
 for(int bi=0;bi<3;bi++)for(int a: {0x3a,0x3b,0x36,0x37}){
  buses[bi]->beginTransmission(a);
  if(buses[bi]->endTransmission()==0){address=a;bus=buses[bi];busIndex=bi;return;}
 }
}
void pollKnob(){
 if(!address){if(millis()-lastScan>1000){scanKnob();lastScan=millis();}return;}
 int n=bus->requestFrom(address,4);
 if(n!=4){while(bus->available())bus->read();knobOk=false;readErrors++;return;}
 bus->read();int lo=bus->read(),hi=bus->read();bool down=bus->read()!=0;
 position=(int16_t)(lo|(hi<<8));knobOk=true;
 if(!initialized){lastPosition=position;rawPressed=pressed=down;changedAt=downAt=millis();initialized=true;return;}
 int delta=(int16_t)(position-lastPosition);lastPosition=position;
 if(delta){rotations+=delta;if(answerCount>0)selected=((selected+delta)%answerCount+answerCount)%answerCount;}
 if(down!=rawPressed){rawPressed=down;changedAt=millis();}
 if(rawPressed!=pressed && millis()-changedAt>=30){
  pressed=rawPressed;
  if(pressed){downAt=millis();held=false;}
  else if(!held)clicks++;
 }
 if(pressed && !held && millis()-downAt>=800){holds++;held=true;}
}
String readState(){
 return String("{\"firmware\":\"idk-button-1\",\"knob_ok\":")+(knobOk?"true":"false")+
  ",\"address\":"+address+",\"position\":"+position+",\"pressed\":"+(pressed?"true":"false")+
  ",\"rotations\":"+rotations+",\"clicks\":"+clicks+",\"holds\":"+holds+
  ",\"state\":"+uiState+",\"selected\":"+selected+",\"answer_count\":"+answerCount+
  ",\"red_led\":"+(redLed?"true":"false")+
  ",\"frames\":"+frames+",\"lit_pixels\":"+litPixels+",\"frame_hash\":"+frameHash+",\"read_errors\":"+readErrors+"}";
}
String setState(int state,int selection,int count){
 uiState=constrain(state,0,6);answerCount=constrain(count,0,3);
 if(selection>=0)selected=answerCount?constrain(selection,0,answerCount-1):0;
 else if(answerCount)selected%=answerCount;else selected=0;
 return String("{\"ok\":true}");
}
String setRedLed(int enabled){
 redLed=enabled!=0;digitalWrite(RED_LED_PIN,redLed?HIGH:LOW);
 return String("{\"ok\":true,\"red_led\":")+(redLed?"true}":"false}");
}
void render(){
 uint8_t pixels[104]={};unsigned long t=millis();
 const uint8_t digits[3][7]={{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},{30,1,1,14,1,1,30}};
 bool showNumber=(uiState==4||uiState==5)&&answerCount>0;
 if(showNumber){
  int brightness=(uiState==5&&((t/180)%2))?2:7;
  for(int y=0;y<7;y++)for(int x=0;x<5;x++)if(digits[selected][y]&(1<<(4-x)))pixels[y*13+x+4]=brightness;
  for(int i=0;i<answerCount;i++)pixels[7*13+4+i*2]=(i==selected)?7:1;
 }else if(uiState==1){
  if((t/450)%2==0)for(int y=2;y<6;y++)for(int x=5;x<8;x++)pixels[y*13+x]=5;
 }else if(uiState==2||uiState==3){
  int x=(t/(uiState==2?100:60))%13;
  for(int y=0;y<8;y++)pixels[y*13+x]=6;
  if(uiState==3)for(int c=0;c<13;c++)pixels[7*13+c]=2;
 }else if(uiState==6){
  if((t/200)%2==0)for(int y=0;y<8;y++){pixels[y*13+y+2]=6;pixels[y*13+9-y]=6;}
 }else{pixels[3*13+6]=((t/800)%2)?1:3;}
 if(pressed)pixels[0]=7;
 litPixels=0;frameHash=2166136261u;
 for(int i=0;i<104;i++){if(pixels[i])litPixels++;frameHash=(frameHash^pixels[i])*16777619u;}
 matrix.draw(pixels);frames++;
}
void setup(){
 pinMode(RED_LED_PIN,OUTPUT);digitalWrite(RED_LED_PIN,LOW);
 matrix.begin();matrix.setGrayscaleBits(3);Wire1.begin();Wire2.begin();Wire.begin();Wire1.setClock(100000);Wire2.setClock(100000);Wire.setClock(100000);scanKnob();
 delay(2000);Bridge.begin();
 while(!Bridge.provide("idk.read",readState))delay(100);
 while(!Bridge.provide("idk.set",setState))delay(100);
 while(!Bridge.provide("idk.led",setRedLed))delay(100);
 Bridge.provide("knob.read",readState);
}
void loop(){pollKnob();render();delay(10);}
